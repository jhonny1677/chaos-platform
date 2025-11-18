// Jenkins Job DSL — defines the load-test-trigger pipeline job.
// Starts a load test, streams live stats every 10 seconds, fails if error rate > 5%.

pipelineJob('load-test-trigger') {
    description 'Start a load test via the Load Tester API. Streams live stats. Fails if error rate > 5%.'

    parameters {
        choiceParam('SCENARIO_TYPE',
            ['smoke', 'stress', 'spike', 'soak'],
            'Load test scenario: smoke=10VU/60s, stress=ramp to breaking point, spike=sudden surge, soak=30min')
        stringParam('TARGET_URL',
            'http://target-app.target-app:8000',
            'HTTP base URL of the service to load test')
        stringParam('VIRTUAL_USERS', '20',
            'Number of concurrent virtual users (ignored for smoke/soak which have fixed VUs)')
        stringParam('DURATION_MINUTES', '5',
            'Test duration in minutes (ignored for smoke which runs exactly 60 seconds)')
        stringParam('MAX_ERROR_RATE_PCT', '5',
            'Build fails if the final error rate exceeds this percentage')
    }

    definition {
        cps {
            sandbox true
            script '''
pipeline {
    agent { label 'python' }

    options {
        timeout(time: 60, unit: 'MINUTES')
        ansiColor('xterm')
        timestamps()
    }

    environment {
        LOADTEST_API = credentials('loadtest-api-url')
        SLACK_HOOK   = credentials('slack-webhook')
    }

    stages {
        stage('Validate') {
            steps {
                sh """
                    curl -sf --max-time 5 \\$LOADTEST_API/health || {
                        echo "\\033[31mERROR: Load Tester unreachable at \\$LOADTEST_API\\033[0m"
                        exit 1
                    }
                    echo "\\033[32mLoad Tester reachable\\033[0m"
                    curl -sf --max-time 5 ${env.TARGET_URL}/health || {
                        echo "\\033[31mWARN: Target URL not responding at ${env.TARGET_URL}\\033[0m"
                    }
                """
            }
        }

        stage('Start Load Test') {
            steps {
                script {
                    def body = groovy.json.JsonOutput.toJson([
                        name: "jenkins-${env.SCENARIO_TYPE}-${env.BUILD_NUMBER}",
                        target_url: env.TARGET_URL,
                        scenario_type: env.SCENARIO_TYPE,
                        virtual_users: env.VIRTUAL_USERS.toInteger(),
                        duration_seconds: env.DURATION_MINUTES.toInteger() * 60,
                        ramp_strategy: 'linear',
                        ramp_duration_seconds: 30
                    ])

                    def response = sh(
                        script: """curl -sf -X POST \\
                            -H 'Content-Type: application/json' \\
                            -d '${body.replace("'", "\\'")}' \\
                            \\$LOADTEST_API/tests""",
                        returnStdout: true
                    ).trim()

                    def json = readJSON(text: response)
                    env.TEST_ID = json.test_id
                    echo "\\033[32mLoad test started: ${env.TEST_ID}\\033[0m"
                    echo "Scenario: ${env.SCENARIO_TYPE} | VUs: ${env.VIRTUAL_USERS} | Duration: ${env.DURATION_MINUTES}m"
                }
            }
        }

        stage('Stream Live Stats') {
            steps {
                script {
                    def maxDuration = env.DURATION_MINUTES.toInteger() + 2
                    def elapsed    = 0
                    def done       = false

                    while (!done && elapsed < maxDuration * 60) {
                        sleep(10)
                        elapsed += 10

                        // Fetch live stats snapshot
                        def statsResp = sh(
                            script: "curl -sf \\$LOADTEST_API/results/live/${env.TEST_ID} 2>/dev/null || echo '{}'",
                            returnStdout: true
                        ).trim()
                        def stats = readJSON(text: statsResp)

                        if (stats) {
                            def rps      = stats.requests_per_second ?: 0
                            def p99      = stats.p99_ms ?: 0
                            def errPct   = stats.total_requests > 0
                                ? (stats.failed_requests / stats.total_requests * 100)
                                : 0
                            def workers  = stats.active_workers ?: 0

                            echo "[${elapsed}s] RPS: ${String.format('%.1f', rps)} | " +
                                 "p99: ${String.format('%.0f', p99)}ms | " +
                                 "Errors: ${String.format('%.1f', errPct)}% | " +
                                 "VUs: ${workers}"

                            // Early exit if error rate is catastrophic (>50%)
                            if (errPct > 50 && stats.total_requests > 100) {
                                echo "\\033[31mError rate catastrophic (${errPct}%) — stopping test early\\033[0m"
                                sh "curl -sf -X POST \\$LOADTEST_API/tests/${env.TEST_ID}/stop || true"
                                break
                            }
                        }

                        // Check if test completed
                        def statusResp = sh(
                            script: "curl -sf \\$LOADTEST_API/tests/${env.TEST_ID} 2>/dev/null || echo '{\"status\":\"unknown\"}'",
                            returnStdout: true
                        ).trim()
                        def testInfo = readJSON(text: statusResp)

                        if (testInfo.status in ['completed', 'stopped', 'failed']) {
                            done = true
                            env.TEST_STATUS = testInfo.status
                            env.FINAL_RPS   = testInfo.summary?.peak_rps?.toString() ?: 'N/A'
                            env.FINAL_ERR   = testInfo.summary?.error_rate_pct?.toString() ?: '0'
                            env.FINAL_P99   = testInfo.summary?.p99_ms?.toString() ?: 'N/A'

                            // Write final report
                            writeFile file: 'load-test-report.json', text: statusResp
                        }
                    }

                    if (!done) {
                        env.TEST_STATUS = 'timeout'
                        env.FINAL_ERR   = '0'
                    }
                }
            }
        }

        stage('Evaluate Result') {
            steps {
                script {
                    echo "=== Load Test Summary ==="
                    echo "ID:           ${env.TEST_ID}"
                    echo "Scenario:     ${env.SCENARIO_TYPE}"
                    echo "Status:       ${env.TEST_STATUS}"
                    echo "Peak RPS:     ${env.FINAL_RPS}"
                    echo "p99 latency:  ${env.FINAL_P99}ms"
                    echo "Error rate:   ${env.FINAL_ERR}%"

                    def maxErr = env.MAX_ERROR_RATE_PCT.toDouble()
                    def actErr = (env.FINAL_ERR ?: '0').toDouble()

                    if (actErr > maxErr) {
                        error "Error rate ${actErr}% exceeds threshold ${maxErr}% — build failed"
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'load-test-report.json', allowEmptyArchive: true

            script {
                def passed = (env.FINAL_ERR ?: '0').toDouble() <= (env.MAX_ERROR_RATE_PCT ?: '5').toDouble()
                def emoji  = passed ? ':white_check_mark:' : ':x:'
                def color  = passed ? 'good' : 'danger'
                def msg = "${emoji} *Load Test* `${env.SCENARIO_TYPE}` → `${env.TARGET_URL}`\\n" +
                          "Status: `${env.TEST_STATUS}` | RPS: `${env.FINAL_RPS}` | " +
                          "p99: `${env.FINAL_P99}ms` | Errors: `${env.FINAL_ERR}%`\\n" +
                          "Build: ${env.BUILD_URL}"

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
