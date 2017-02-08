#!/usr/bin/env bash

#cleanup exited containers
docker rm -v $(docker ps -a -q -f status=exited)

#cleanup dangling images
docker rmi $(docker images -f "dangling=true" -q)

#run docker cleanup container
docker run -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/docker:/var/lib/docker --rm martin/docker-cleanup-volumes

#cleanup volumes
docker volume ls -qf dangling=true | xargs -r docker volume rm