# Jenkins LTS with JDK 17 — pre-installed plugins, AWS CLI, and kubectl.
# Build agents run as ephemeral Kubernetes pods (numExecutors=0 on controller).

FROM jenkins/jenkins:lts-jdk17

# ── Install Jenkins plugins (as jenkins user) ───────────────────────────────
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli \
      --plugin-file /usr/share/jenkins/ref/plugins.txt \
      --verbose

# ── Install system tools (switch to root) ────────────────────────────────────
USER root

# Install base utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      unzip \
      jq \
      git \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" \
      -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp/ \
    && /tmp/aws/install \
    && rm -rf /tmp/awscliv2.zip /tmp/aws \
    && aws --version

# Install kubectl (latest stable)
RUN KUBECTL_VER=$(curl -fsSL https://dl.k8s.io/release/stable.txt) \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VER}/bin/linux/amd64/kubectl" \
         -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && kubectl version --client

# ── Copy JCasC configuration ─────────────────────────────────────────────────
COPY jenkins.yaml /var/jenkins_home/casc_configs/jenkins.yaml
RUN chown jenkins:jenkins /var/jenkins_home/casc_configs/jenkins.yaml

# ── Back to jenkins user ─────────────────────────────────────────────────────
USER jenkins

# Tell Jenkins where to find Configuration-as-Code config
ENV CASC_JENKINS_CONFIG /var/jenkins_home/casc_configs/jenkins.yaml

# Disable the setup wizard — everything configured via JCasC
ENV JAVA_OPTS "-Djenkins.install.runSetupWizard=false -Dhudson.model.DirectoryBrowserSupport.CSP="

EXPOSE 8080 50000

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD curl -sf http://localhost:8080/login || exit 1
