"""One explicit local Docker Engine endpoint for the Agent00X prototype."""

LOCAL_DOCKER_HOST = "unix:///var/run/docker.sock"
LOCAL_DOCKER_HOST_ARGUMENT = f"--host={LOCAL_DOCKER_HOST}"
