FROM centos/python-36-centos7

USER root
RUN pip install --upgrade pip

# Setup Deployer
ADD / /deployer
WORKDIR /deployer
RUN python setup.py sdist
RUN pip install dist/deployer-0.3.11.tar.gz

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace
