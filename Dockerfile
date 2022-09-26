FROM python

# Perform updates
RUN pip install --upgrade pip
RUN apt-get update

# Setup Deployer
COPY ./ /
RUN python setup.py sdist
RUN pip install dist/deployer-*.tar.gz

# Install node
RUN curl -sL https://apt.nodesource.com/setup_14.x | bash -
RUN apt-get install nodejs -y

# Prep workspace
RUN mkdir ~/.npm

# Permissions
RUN chmod -R 757 ~/.npm

# Clean
RUN apt-get clean -y

CMD /opt/app-root/bin/deployer
