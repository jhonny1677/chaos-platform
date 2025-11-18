// Jenkins Job DSL — defines the chaos-experiment-trigger pipeline job.
// The seed job reads this file and creates/updates the job automatically.

pipelineJob('chaos-experiment-trigger') {
    description 'Trigger a chaos experiment via the Chaos Engine API and poll until complete.'
    keepDependencies false

    parameters {
        choiceParam('EXPERIMENT_TYPE',
            ['pod_kill', 'network_delay', 'cpu_stress', 'memory_stress'],
            'Type of chaos to inject into the target system')
        stringParam('TARGET_NAMESPACE', 'target-app',
            'Kubernetes namespace containing the target pods')
        stringParam('TARGET_LABEL', 'app=target-app',
            'Kubernetes label selector for pods to target')
        stringParam('DURATION_MINUTES', '5',
            'Maximum experiment duration in minutes (chaos stops after this time)')
        stringParam('KILL_PERCENTAGE', '30',
            'For pod_kill: percentage of pods to kill (capped at 50% by engine)')
        stringParam('LATENCY_MS', '200',
            'For network_delay: injected latency in milliseconds')
    }

    definition {
        cps {
            sandbox true
            script '''
pipeline {
    agent { label 'python' }

    options {
        timeout(time: 30, unit: 'MINUTES')
        ansiColor('xterm')
        timestamps()
    }

    environment {
        CHAOS_API    = credentials('chaos-api-url')
        SLACK_HOOK   = credentials('slack-webhook')
    }

    stages {
        stage('Validate') {
            steps {
                sh 'python3 -c "import urllib.request" && echo "Python OK"'
                sh """
                    curl -sf --max-time 5 \\$CHAOS_API/health || {
                        echo "\\033[31mERROR: Chaos Engine unreachable at \\$CHAOS_API\\033[0m"
                        exit 1
                    }
                    echo "\\033[32mChaos Engine reachable\\033[0m"
                """
            }
        }

        stage('Create Experiment') {
            steps {
                script {
                    // Build parameters map based on experiment type
                    def params = [kill_percentage: env.KILL_PERCENTAGE.toInteger()]
                    if (env.EXPERIMENT_TYPE == 'network_delay') {
                        params = [latency_ms: env.LATENCY_MS.toInteger(),
                                  jitter_ms: 20,
                                  duration_seconds: env.DURATION_MINUTES.toInteger() * 60]
                    } else if (env.EXPERIMENT_TYPE in ['cpu_stress', 'memory_stress']) {
                        params = [duration_seconds: env.DURATION_MINUTES.toInteger() * 60,
                                  cpu_percentage: 80, memory_mb: 512]
                    }

                    def paramsJson = groovy.json.JsonOutput.toJson(params)
                    def body = groovy.json.JsonOutput.toJson([
                        name: "jenkins-${env.EXPERIMENT_TYPE}-${env.BUILD_NUMBER}",
                        description: "Triggered by Jenkins job #${env.BUILD_NUMBER} — ${env.BUILD_URL}",
                        chaos_type: env.EXPERIMENT_TYPE,
                        target_namespace: env.TARGET_NAMESPACE,
                        target_label_selector: env.TARGET_LABEL,
                        parameters: params,
                        steady_state_thresholds: [
                            error_rate_percent: 5.0,
                            latency_p99_ms: 2000,
                            min_ready_pods: 1
                        ]
                    ])

                    def response = sh(
                        script: """curl -sf -X POST \\
                            -H 'Content-Type: application/json' \\
                            -d '${body.replace("'", "\\'")}' \\
                            \\$CHAOS_API/experiments""",
                        returnStdout: true
                    ).trim()

                    def json = readJSON(text: response)
                    env.EXPERIMENT_ID = json.experiment_id
                    echo "\\033[32mExperiment created: ${env.EXPERIMENT_ID}\\033[0m"
                    echo "Chaos type: ${env.EXPERIMENT_TYPE} | Target: ${env.TARGET_NAMESPACE}"
                }
            }
        }

        stage('Poll Until Complete') {
            steps {
                script {
                    def maxWait = env.DURATION_MINUTES.toInteger() + 5
                    def elapsed = 0
                    def done = false

                    while (!done && elapsed < maxWait * 60) {
                        sleep(30)
                        elapsed += 30

                        def resp = sh(
                            script: "curl -sf \\$CHAOS_API/experiments/${env.EXPERIMENT_ID}",
                            returnStdout: true
                        ).trim()
                        def exp = readJSON(text: resp)

                        echo "[${elapsed}s] Status: ${exp.status}"

                        if (exp.status in ['completed', 'failed', 'aborted']) {
                            done = true
                            env.FINAL_STATUS    = exp.status
                            env.HYPOTHESIS_PASS = exp.result_summary?.hypothesis_passed?.toString() ?: 'unknown'
                            env.RECOVERY_TIME   = exp.result_summary?.recovery_time_seconds?.toString() ?: 'N/A'
                            env.ERROR_RATE      = exp.result_summary?.error_rate_during?.toString() ?: 'N/A'

                            // Write full result as artifact
                            writeFile file: 'experiment-report.json', text: resp
                            echo "\\033[32mExperiment finished: ${env.FINAL_STATUS}\\033[0m"
                        }
                    }

                    if (!done) {
                        error "Experiment did not complete within ${maxWait} minutes"
                    }
                }
            }
        }

        stage('Evaluate Result') {
            steps {
                script {
                    echo "=== Experiment Summary ==="
                    echo "ID:              ${env.EXPERIMENT_ID}"
                    echo "Type:            ${env.EXPERIMENT_TYPE}"
                    echo "Final status:    ${env.FINAL_STATUS}"
                    echo "Hypothesis pass: ${env.HYPOTHESIS_PASS}"
                    echo "Error rate:      ${env.ERROR_RATE}%"
                    echo "Recovery time:   ${env.RECOVERY_TIME}s"

                    if (env.FINAL_STATUS == 'failed' && env.HYPOTHESIS_PASS == 'false') {
                        unstable "Steady-state hypothesis was violated — system did not recover as expected"
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'experiment-report.json', allowEmptyArchive: true

            script {
                def emoji   = (env.FINAL_STATUS == 'completed') ? ':white_check_mark:' : ':x:'
                def color   = (env.FINAL_STATUS == 'completed') ? 'good' : 'danger'
                def message = "${emoji} *Chaos Experiment* `${env.EXPERIMENT_TYPE}` on `${env.TARGET_NAMESPACE}`\\n" +
                              "Status: `${env.FINAL_STATUS}` | Hypothesis: `${env.HYPOTHESIS_PASS}` | " +
                              "Error rate: `${env.ERROR_RATE}%` | Recovery: `${env.RECOVERY_TIME}s`\\n" +
                              "Build: ${env.BUILD_URL}"

                sh """curl -sf -X POST \\
                    -H 'Content-type: application/json' \\
                    --data '{"text":"${message}","color":"${color}"}' \\
                    \\$SLACK_HOOK || true"""
            }
        }
    }
}
'''
        }
    }
}
