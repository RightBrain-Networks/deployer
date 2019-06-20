FROM centos/python-36-centos7

USER root

# Perform updates
RUN pip install --upgrade pip
RUN yum update -y

# Setup Deployer
ADD / /deployer
WORKDIR /deployer
RUN python setup.py sdist
RUN pip install dist/deployer-*.tar.gz



# Install node
RUN wget https://nodejs.org/download/release/latest-v12.x/node-v12.4.0-linux-x64.tar.gz
RUN tar --strip-components 1 -xzvf node-v* -C /usr/local
RUN npm install -g npm


# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace

# Permissions
RUN useradd -d /deployerUser deployerUser
RUN chown -R deployerUser:deployerUser ~/.npm
RUN chown -R deployerUser:deployerUser /workspace
RUN chmod -R 770 ~/.npm

CMD /opt/app-root/bin/deployer

USER deployerUser

RUN whoami