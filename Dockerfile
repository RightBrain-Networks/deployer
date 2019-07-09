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
RUN curl -sL https://rpm.nodesource.com/setup_10.x | bash -
RUN yum install nodejs -y

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace
RUN mkdir ~/.npm

# Permissions
RUN useradd -d /deployerUser deployerUser
RUN chown -R deployerUser:deployerUser ~/.npm
RUN chown -R deployerUser:deployerUser /workspace
RUN chmod -R 757 ~/.npm

CMD /opt/app-root/bin/deployer

USER deployerUser