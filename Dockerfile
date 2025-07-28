FROM registry.access.redhat.com/ubi9/python-311:latest

RUN pip install --upgrade pip

COPY requirements/requirements.in /tmp/requirements.in
COPY requirements/requirements_dev.in /tmp/requirements_dev.in

RUN pip install -r /tmp/requirements.in
RUN pip install -r /tmp/requirements_dev.in
