# should be run from the root of sources. Ex:
# $ docker build -t <some tag> -f deployment/docker/Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.7-slim

RUN apt-get update && apt-get install -y inotify-tools openssh-server build-essential nginx git
RUN pip install pip -U

# Set the working directory to /app
WORKDIR /app

# Minimal files for preparing environment
COPY deployment ./deployment
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt -U

# Copy the current directory contents into the container at /app
COPY bin ./bin
COPY config/*.default.py ./config/
COPY cloud_mailing ./cloud_mailing
COPY static ./static
COPY ssl ./ssl


#WORKDIR /app/cloud_mailing
#RUN cd cloud_mailing && python setup.py develop
#RUN pip install fabric -U

ARG SERIAL
ARG API_KEY
ARG INIT_PY

# Make port 80 available to the world outside this container
EXPOSE 33610 33620

# Define environment variable
ENV NAME CloudMailing

# Run app.py when the container launches
CMD ["python", '-O', "bin/cm_master.py"]
#CMD ["python", '-O', "$INIT_PY"]
