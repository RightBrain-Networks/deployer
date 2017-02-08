FROM 356438515751.dkr.ecr.us-east-1.amazonaws.com/base
RUN useradd -d /vibeio vibeio  # Create 'vibeio' user
WORKDIR /var


# Add files from host to container dir
ADD /vibeio/vibeio/setup.cfg /vibeio/vibeio/development.ini  /var/vibeio/
ADD /vibeio/README.md /var/vibeio/README.txt
ADD /vibeio/CHANGES.txt /var/vibeio/CHANGES.txt
ADD /vibeio/vibeio/setup.py /var/vibeio/setup.py
ADD /vibeio/vibeio/vibeio /var/vibeio/

RUN chown -R vibeio:vibeio /var/vibeio && chmod -R ug+x /var/vibeio/*

RUN yum update -y && yum install -y epel-release

RUN yum install -y python-devel
RUN yum install -y python-pip
RUN pip install --upgrade pip
RUN pip install -U pip wheel setuptools
RUN yum install postgresql-libs postgresql postgresql-server -y
RUN yum install gcc postgresql-devel libffi-devel openssl-devel -y



RUN python /var/vibeio/setup.py develop

EXPOSE 5001
USER vibeio
CMD pserve development.ini
