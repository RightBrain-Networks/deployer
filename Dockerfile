FROM ubuntu:trusty
# Python requirements
RUN apt-get update && \
    apt-get install -y python python-dev python-pip gcc

# Setup Deployer
ADD / /deployer
WORKDIR /deployer
RUN python setup.py sdist
RUN pip install -r dist/deployer-0.3.5.tar.gz

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace
