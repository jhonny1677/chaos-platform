// Jenkins Job DSL — nightly chaos pipeline.
// Runs at 02:00 every weeknight: smoke → pod kill → load test → combined report → Slack.

pipelineJob('nightly-chaos') {
    description 'Nightly chaos pipeline: smoke test → pod kill → load test → report.'

    triggers {
        // Run at 02:00 Mon–Fri
        cron('0 2 * * 1-5')
    }

    definition {
        cps {
            sandbox true
            script '''
pipeline {
    agent { label 'python' }

    options {
        timeout(time: 90, unit: 'MINUTES')
        ansiColor('xterm')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    environment {
        CHAOS_API    = credentials('chaos-api-url')
        LOADTEST_API = credentials('loadtest-api-url')
        SLACK_HOOK   = credentials('slack-webhook')
        TARGET_NS    = 'target-app'
    }

    stages {
        // ── Stage 1: Smoke Test — verify system health before chaos ──────────
        stage('Smoke Test') {
            steps {
                script {
                    echo "\\033[34m=== Smoke Test: verifying system health ===\\033[0m"
                    def body = groovy.json.JsonOutput.toJson([
                        name: "nightly-smoke-${env.BUILD_NUMBER}",
                        target_url: "http://target-app.target-app:8000",
                        scenario_type: 'smoke',
                        virtual_users: 10,
                        duration_seconds: 60,
                        ramp_strategy: 'instant'
                    ])

                    def resp = sh(
                        script: """curl -sf -X POST \\
                            -H 'Content-Type: application/json' \\
                            -d '${body.replace("'", "\\'")}' \\
                            \\$LOADTEST_API/tests""",
                        returnStdout: true
                    ).trim()
                    env.SMOKE_ID = readJSON(text: resp).test_id
                    echo "Smoke test started: ${env.SMOKE_ID}"

                    // Wait 90 seconds for smoke test to complete
                    sleep(90)

                    def result = sh(
                        script: "curl -sf \\$LOADTEST_API/tests/${env.SMOKE_ID}",
                        returnStdout: true
                    ).trim()
                    def smoke = readJSON(text: result)
                    env.SMOKE_STATUS = smoke.status
                    env.SMOKE_ERR    = smoke.summary?.error_rate_pct?.toString() ?: '0'

                    echo "Smoke status: ${env.SMOKE_STATUS} | Error rate: ${env.SMOKE_ERR}%"

                    if (env.SMOKE_STATUS != 'completed' || env.SMOKE_ERR.toDouble() > 1.0) {
                        error "Smoke test FAILED — system is unhealthy. Aborting chaos injection. " +
                              "Status: ${env.SMOKE_STATUS}, Error rate: ${env.SMOKE_ERR}%"
                    }
                    echo "\\033[32mSystem healthy — proceeding with chaos injection\\033[0m"
                }
            }
        }

        // ── Stage 2: Pod Kill Experiment ─────────────────────────────────────
        stage('Chaos: Pod Kill') {
            steps {
                script {
                    echo "\\033[31m=== Injecting pod kill chaos ===\\033[0m"
                    def body = groovy.json.JsonOutput.toJson([
                        name: "nightly-pod-kill-${env.BUILD_NUMBER}",
                        description: "Nightly chaos run — build ${env.BUILD_NUMBER}",
                        chaos_type: 'pod_kill',
                        target_namespace: env.TARGET_NS,
                        target_label_selector: "app=${env.TARGET_NS}",
                        parameters: [kill_percentage: 30],
                        steady_state_thresholds: [
                            error_rate_percent: 5.0,
                            latency_p99_ms: 2000,
                            min_ready_pods: 1
                        ]
                    ])

                    def resp = sh(
                        script: """curl -sf -X POST \\
                            -H 'Content-Type: application/json' \\
                            -d '${body.replace("'", "\\'")}' \\
                            \\$CHAOS_API/experiments""",
                        returnStdout: true
                    ).trim()
                    env.EXP_ID = readJSON(text: resp).experiment_id
                    echo "Experiment started: ${env.EXP_ID}"

                    // Poll until experiment completes (max 15 min)
                    def elapsed = 0
                    def done    = false
                    while (!done && elapsed < 900) {
                        sleep(30); elapsed += 30
                        def expResp = sh(
                            script: "curl -sf \\$CHAOS_API/experiments/${env.EXP_ID}",
                            returnStdout: true
                        ).trim()
                        def exp = readJSON(text: expResp)
                        echo "[${elapsed}s] Experiment status: ${exp.status}"

                        if (exp.status in ['completed', 'failed', 'aborted']) {
                            done = true
                            env.EXP_STATUS    = exp.status
                            env.EXP_HYPO      = exp.result_summary?.hypothesis_passed?.toString() ?: 'unknown'
                            env.EXP_RECOVERY  = exp.result_summary?.recovery_time_seconds?.toString() ?: 'N/A'
                            writeFile file: 'chaos-report.json', text: expResp
                        }
                    }
                    echo "Chaos finished: ${env.EXP_STATUS} | Hypothesis: ${env.EXP_HYPO} | Recovery: ${env.EXP_RECOVERY}s"
                }
            }
        }

        // ── Stage 3: Post-Chaos Load Test ────────────────────────────────────
        stage('Load Test Post-Chaos') {
            steps {
                script {
                    echo "\\033[34m=== Running load test after chaos ===\\033[0m"

                    // Wait 30s for system to stabilise after chaos
                    sleep(30)

                    def body = groovy.json.JsonOutput.toJson([
                        name: "nightly-stress-${env.BUILD_NUMBER}",
                        target_url: "http://target-app.target-app:8000",
                        scenario_type: 'stress',
                        virtual_users: 100,
                        duration_seconds: 300,
                        ramp_strategy: 'step'
                    ])

                    def resp = sh(
                        script: """curl -sf -X POST \\
                            -H 'Content-Type: application/json' \\
                            -d '${body.replace("'", "\\'")}' \\
                            \\$LOADTEST_API/tests""",
                        returnStdout: true
                    ).trim()
                    env.LOAD_ID = readJSON(text: resp).test_id
                    echo "Load test started: ${env.LOAD_ID}"

                    // Stream stats for 6 minutes
                    def elapsed = 0
                    def done    = false
                    while (!done && elapsed < 400) {
                        sleep(10); elapsed += 10
                        def statsResp = sh(
                            script: "curl -sf \\$LOADTEST_API/results/live/${env.LOAD_ID} 2>/dev/null || echo '{}'",
                            returnStdout: true
                        ).trim()
                        def s = readJSON(text: statsResp)
                        if (s) echo "[${elapsed}s] RPS: ${s.requests_per_second ?: 0} | Errors: ${s.failed_requests ?: 0}"

                        def testResp = sh(
                            script: "curl -sf \\$LOADTEST_API/tests/${env.LOAD_ID}",
                            returnStdout: true
                        ).trim()
                        def t = readJSON(text: testResp)
                        if (t.status in ['completed', 'stopped', 'failed']) {
                            done = true
                            env.LOAD_STATUS = t.status
                            env.LOAD_RPS    = t.summary?.peak_rps?.toString() ?: 'N/A'
                            env.LOAD_ERR    = t.summary?.error_rate_pct?.toString() ?: '0'
                            writeFile file: 'load-report.json', text: testResp
                        }
                    }
                    echo "Load test complete: ${env.LOAD_STATUS} | Peak RPS: ${env.LOAD_RPS} | Errors: ${env.LOAD_ERR}%"
                }
            }
        }

        // ── Stage 4: Generate Combined Report ────────────────────────────────
        stage('Generate Report') {
            steps {
                script {
                    def report = """# Nightly Chaos Report — Build ${env.BUILD_NUMBER}
Date: ${new Date().format('yyyy-MM-dd HH:mm')} UTC

## Smoke Test
Status: ${env.SMOKE_STATUS} | Error rate: ${env.SMOKE_ERR}%

## Chaos Experiment
Type: pod_kill | Status: ${env.EXP_STATUS}
Hypothesis passed: ${env.EXP_HYPO} | Recovery time: ${env.EXP_RECOVERY}s

## Post-Chaos Load Test
Status: ${env.LOAD_STATUS} | Peak RPS: ${env.LOAD_RPS} | Error rate: ${env.LOAD_ERR}%

Build URL: ${env.BUILD_URL}
"""
                    writeFile file: 'nightly-report.md', text: report
                    echo report
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: '*.json,*.md', allowEmptyArchive: true

            script {
                def allOk = (env.SMOKE_STATUS == 'completed') &&
                            (env.EXP_STATUS in ['completed']) &&
                            (env.LOAD_ERR ?: '100').toDouble() < 5
                def emoji = allOk ? ':white_check_mark:' : ':warning:'
                def color = allOk ? 'good' : 'danger'
                def msg   = "${emoji} *Nightly Chaos Run* — Build #${env.BUILD_NUMBER}\\n" +
                            "• Smoke: `${env.SMOKE_STATUS}` (${env.SMOKE_ERR}% errors)\\n" +
                            "• Chaos: `${env.EXP_STATUS}` — hypothesis `${env.EXP_HYPO}`, recovery `${env.EXP_RECOVERY}s`\\n" +
                            "• Load: `${env.LOAD_STATUS}` — peak `${env.LOAD_RPS}` rps, `${env.LOAD_ERR}%` errors\\n" +
                            "Details: ${env.BUILD_URL}"

                sh """curl -sf -X POST \\
                    -H 'Content-type: application/json' \\
                    --data '{"text":"${msg}","color":"${color}"}' \\
                    \\$SLACK_HOOK || true"""
            }
        }
    }
}
'''
        }
    }
}
