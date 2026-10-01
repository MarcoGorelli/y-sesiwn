FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# git, curl and the GitHub CLI
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && curl -fsSL -o /usr/share/keyrings/gh.gpg \
      https://cli.github.com/packages/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/gh.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/gh.list \
 && apt-get update \
 && apt-get install -y gh \
 && rm -rf /var/lib/apt/lists/*

# uv, for the virtualenv and dev requirements
RUN curl -LsSf https://astral.sh/uv/install.sh \
      | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# Non-root user (the Playwright image ships with "pwuser"); give it the
# host's UID/GID so it can write to the bind-mounted repo
ARG UID=1000
ARG GID=1000
RUN (userdel -r ubuntu 2>/dev/null || true) \
 && groupmod -g $GID pwuser \
 && usermod -u $UID -g $GID pwuser \
 && chown -R pwuser:pwuser /home/pwuser
USER pwuser
ENV PATH="/home/pwuser/.local/bin:${PATH}"
RUN curl -fsSL https://claude.ai/install.sh | bash
# Pre-create the volume mount points so the volumes end up owned by pwuser
RUN mkdir -p /home/pwuser/.claude /home/pwuser/.cache/uv
# Keep all of Claude's state (incl. ~/.claude.json) in the persisted volume
ENV CLAUDE_CONFIG_DIR=/home/pwuser/.claude

WORKDIR /work
