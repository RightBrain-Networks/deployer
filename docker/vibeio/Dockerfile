FROM 356438515751.dkr.ecr.us-east-1.amazonaws.com/base
RUN useradd -d /vibeio vibeio  # Create 'vibeio' user
WORKDIR /vibeio


# Add files from host to container dir
ADD /vibeio/vibeio/setup.cfg  /vibeio/
ADD /vibeio/vibeio/development.ini /vibeio/
ADD /vibeio/vibeio/production.ini /vibeio/
ADD /vibeio/README.md /vibeio/README.txt
ADD /vibeio/CHANGES.txt /vibeio/CHANGES.txt
ADD /vibeio/vibeio/setup.py /vibeio/setup.py
ADD /vibeio/vibeio/vibeio /vibeio/vibeio

RUN chown -R vibeio:vibeio /vibeio && chmod -R ug+x /vibeio/*

RUN yum update -y && yum install -y epel-release

RUN yum install -y python-devel
RUN yum install -y python-pip
RUN pip install --upgrade pip
RUN pip install -U pip wheel setuptools
RUN yum install postgresql-libs postgresql postgresql-server -y
RUN yum install gcc postgresql-devel libffi-devel openssl-devel -y



RUN python setup.py develop


EXPOSE 7666
CMD pserve production.ini
