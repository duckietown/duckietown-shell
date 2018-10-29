FROM ubuntu:18.04
ENV REF=2
RUN apt-get update
RUN apt-get install -y python3 python3-pip
RUN apt-get install -y git
RUN pip3 install duckietown-shell

RUN apt-get install -y curl

WORKDIR /dts-test

ARG TOKEN
ENV TOKEN=${TOKEN}

ARG DOCKER_USERNAME
ENV DOCKER_USERNAME=${DOCKER_USERNAME}

COPY 05_install_dts.sh .
RUN ./05_install_dts.sh

COPY 10_authenticate.sh .
RUN ./10_authenticate.sh

COPY 15_challenges_config.sh .
RUN ./15_challenges_config.sh

COPY 16_install_docker.sh .
RUN ./16_install_docker.sh

# run after the build

COPY 20_challenges_submit.sh .

COPY after_build.sh .
CMD ./after_build.sh
