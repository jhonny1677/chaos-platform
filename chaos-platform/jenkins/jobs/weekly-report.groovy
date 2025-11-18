// Jenkins Job DSL — weekly report pipeline.
// Runs every Monday morning: queries both APIs for last 7 days → markdown report → email + Slack.

pipelineJob('weekly-report') {
    description 'Generate a weekly summary of all chaos experiments and load tests from the past 7 days.'

    triggers {
        // Every Monday at 08:00 UTC
        cron('0 8 * * 1')
    }

    definition {
        cps {
            sandbox true
            script '''
pipeline {
    agent { label 'python' }

    options {
        timeout(time: 15, unit: 'MINUTES')
        ansiColor('xterm')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '52'))  // Keep 1 year of weekly reports
    }

    environment {
        CHAOS_API    = credentials('chaos-api-url')
        LOADTEST_API = credentials('loadtest-api-url')
        SLACK_HOOK   = credentials('slack-webhook')
    }

    stages {
        stage('Fetch Experiments') {
            steps {
                script {
                    echo "\\033[34m=== Fetching experiments from last 7 days ===\\033[0m"
                    def resp = sh(
                        script: "curl -sf \\$CHAOS_API/experiments",
                        returnStdout: true
                    ).trim()
                    def data = readJSON(text: resp)
                    def experiments = data.experiments ?: data ?: []

                    // Filter to last 7 days
                    def cutoff = new Date() - 7
                    def recent = experiments.findAll { exp ->
                        def created = Date.parse("yyyy-MM-dd", (exp.created_at ?: '').take(10)) ?: new Date(0)
                        created >= cutoff
                    }

                    env.EXP_TOTAL     = recent.size().toString()
                    env.EXP_COMPLETED = recent.count { it.status == 'completed' }.toString()
                    env.EXP_FAILED    = recent.count { it.status == 'failed' }.toString()
                    env.EXP_HYPO_PASS = recent.count { it.result_summary?.hypothesis_passed == true }.toString()

                    def avgRecovery = recent
                        .findAll { it.result_summary?.recovery_time_seconds != null }
                        .collect { it.result_summary.recovery_time_seconds as Double }
                    env.AVG_RECOVERY = avgRecovery ? String.format('%.1f', avgRecovery.sum() / avgRecovery.size()) : 'N/A'

                    // Write full data for report
                    writeFile file: 'experiments-raw.json', text: resp
                    echo "Found ${env.EXP_TOTAL} experiments in the last 7 days"
                }
            }
        }

        stage('Fetch Load Tests') {
            steps {
                script {
                    echo "\\033[34m=== Fetching load tests from last 7 days ===\\033[0m"
                    def resp = sh(
                        script: "curl -sf \\$LOADTEST_API/tests",
                        returnStdout: true
                    ).trim()
                    def data = readJSON(text: resp)
                    def tests = data.tests ?: data ?: []

                    def cutoff = new Date() - 7
                    def recent = tests.findAll { t ->
                        def created = Date.parse("yyyy-MM-dd", (t.created_at ?: '').take(10)) ?: new Date(0)
                        created >= cutoff
                    }

                    env.TEST_TOTAL     = recent.size().toString()
                    env.TEST_COMPLETED = recent.count { it.status == 'completed' }.toString()
                    env.TEST_FAILED    = recent.count { it.status == 'failed' }.toString()

                    def peakRpsAll = recent
                        .findAll { it.summary?.peak_rps != null }
                        .collect { it.summary.peak_rps as Double }
                    env.MAX_PEAK_RPS = peakRpsAll ? String.format('%.1f', peakRpsAll.max()) : 'N/A'

                    def errRates = recent
                        .findAll { it.summary?.error_rate_pct != null }
                        .collect { it.summary.error_rate_pct as Double }
                    env.AVG_ERR_RATE = errRates ? String.format('%.2f', errRates.sum() / errRates.size()) : 'N/A'

                    writeFile file: 'tests-raw.json', text: resp
                    echo "Found ${env.TEST_TOTAL} load tests in the last 7 days"
                }
            }
        }

        stage('Generate Report') {
            steps {
                script {
                    def now      = new Date().format('yyyy-MM-dd')
                    def weekAgo  = (new Date() - 7).format('yyyy-MM-dd')
                    def report   = """# Chaos Platform Weekly Report
**Period:** ${weekAgo} → ${now}
**Generated:** ${new Date().format('yyyy-MM-dd HH:mm')} UTC by Jenkins Build #${env.BUILD_NUMBER}

---

## Chaos Experiments Summary

| Metric | Value |
|--------|-------|
| Total experiments | ${env.EXP_TOTAL} |
| Completed | ${env.EXP_COMPLETED} |
| Failed | ${env.EXP_FAILED} |
| Hypothesis passed | ${env.EXP_HYPO_PASS} |
| Avg recovery time | ${env.AVG_RECOVERY}s |

## Load Tests Summary

| Metric | Value |
|--------|-------|
| Total tests | ${env.TEST_TOTAL} |
| Completed | ${env.TEST_COMPLETED} |
| Failed | ${env.TEST_FAILED} |
| Peak RPS (max) | ${env.MAX_PEAK_RPS} req/s |
| Avg error rate | ${env.AVG_ERR_RATE}% |

---

## Observations

${env.EXP_FAILED.toInteger() > 0 ? "⚠️ **${env.EXP_FAILED} chaos experiment(s) failed** — review circuit breaker state and steady-state thresholds." : "✅ All chaos experiments completed successfully."}
${env.AVG_ERR_RATE != 'N/A' && env.AVG_ERR_RATE.toDouble() > 5 ? "⚠️ **Average error rate ${env.AVG_ERR_RATE}% exceeds 5% SLO** — investigate load test results." : "✅ Error rates within acceptable range."}
${env.AVG_RECOVERY != 'N/A' && env.AVG_RECOVERY.toDouble() > 120 ? "⚠️ **Average recovery time ${env.AVG_RECOVERY}s is high** — consider improving pod restart policies." : "✅ Recovery times healthy."}

---
*Report generated by chaos-platform Jenkins weekly-report job.*
*Build: ${env.BUILD_URL}*
"""
                    writeFile file: 'weekly-report.md', text: report
                    echo report
                    env.REPORT_TEXT = report
                }
            }
        }

        stage('Distribute Report') {
            parallel {
                stage('Post to Slack') {
                    steps {
                        script {
                            def emoji = (env.EXP_FAILED.toInteger() == 0 && env.TEST_FAILED.toInteger() == 0)
                                        ? ':bar_chart:' : ':warning:'
                            def msg = "${emoji} *Weekly Chaos Platform Report*\\n" +
                                      "• Experiments: ${env.EXP_COMPLETED}/${env.EXP_TOTAL} completed, " +
                                        "${env.EXP_HYPO_PASS} hypothesis passes, " +
                                        "avg recovery ${env.AVG_RECOVERY}s\\n" +
                                      "• Load Tests: ${env.TEST_COMPLETED}/${env.TEST_TOTAL} completed, " +
                                        "peak ${env.MAX_PEAK_RPS} rps, " +
                                        "avg ${env.AVG_ERR_RATE}% error rate\\n" +
                                      "Full report: ${env.BUILD_URL}artifact/weekly-report.md"

                            sh """curl -sf -X POST \\
                                -H 'Content-type: application/json' \\
                                --data '{"text":"${msg}"}' \\
                                \\$SLACK_HOOK || true"""
                        }
                    }
                }

                stage('Email Report') {
                    steps {
                        emailext(
                            to: 'team@chaos-platform.local',
                            subject: "Chaos Platform Weekly Report — ${new Date().format('yyyy-MM-dd')}",
                            body: readFile('weekly-report.md'),
                            mimeType: 'text/plain',
                            attachmentsPattern: 'weekly-report.md'
                        )
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: '*.md,*.json', allowEmptyArchive: true
        }
    }
}
'''
        }
    }
}
