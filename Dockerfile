# See docker build instructions in README.md.

# Update version tag to match the python version supported in setup.py in the deployer release
FROM python:3.8-buster
ARG VER
USER root

# Perform updates
RUN pip install --upgrade pip
RUN apt-get -y update && \
  apt-get install sed

# Setup Deployer
ADD / /deployer/
WORKDIR /deployer
# TODO: Take desired version as build arg. Checkout the tag. Sed the version number to correct so --version works.
RUN sed -i -E "s/__version__ = '0.0.0'/__version__ = '${VER}'/" deployer/__init__.py
RUN python setup.py sdist
RUN pip install dist/deployer-*.tar.gz

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace

# User
RUN mkdir /deployerUser && useradd -d /deployerUser deployerUser
RUN chown -R deployerUser:deployerUser /workspace

CMD /usr/local/bin/deployer

USER deployerUser
