FROM ubuntu:trusty
# Python requirements
RUN apt-get update && \
    apt-get install -y python python-dev python-pip gcc

# Setup Deployer
ADD / /deployer
RUN pip install -r /deployer/requirements.txt && \
    ln -s /deployer/deployer.py /usr/local/bin/deployer && \
    ln -s /deployer/config_updater.py /usr/local/bin/config_updater 

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace
