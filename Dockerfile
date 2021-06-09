FROM python:3.8-buster

USER root

# Build with this command:
# cat Dockerfile  | docker build -t deployer -f- $PWD

# Perform updates
RUN pip install --upgrade pip
RUN apt-get -y update

# Setup Deployer
ADD / /deployer/
WORKDIR /deployer
RUN python setup.py sdist
RUN pip install dist/deployer-*.tar.gz

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace

# Permissions
RUN useradd -d /deployerUser deployerUser
RUN chown -R deployerUser:deployerUser /workspace

CMD /usr/local/bin/deployer

USER deployerUser
