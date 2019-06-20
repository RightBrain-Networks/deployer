FROM centos/python-36-centos7

USER root
RUN pip install --upgrade pip

# Setup Deployer
ADD / /deployer
WORKDIR /deployer
RUN python setup.py sdist
RUN pip install dist/deployer-*.tar.gz



RUN yum update -y



RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.34.0/install.sh | bash
RUN /opt/app-root/src/.nvm install node
RUN npm install -g npm

RUN npm -v
RUN node -v

RUN mkdir ~/.npm
RUN chmod 777 ~/.npm

# Prep workspace
RUN mkdir /workspace
WORKDIR /workspace
VOLUME /workspace

CMD /opt/app-root/bin/deployer