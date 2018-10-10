FROM billyteves/ubuntu-dind:16.04

COPY . duckietown-shell

RUN apt update && apt install -y \
	python-pip \
	git \
	&& rm -rf /var/lib/apt/lists/*

RUN cd duckietown-shell && \
    pip install python-dateutil && \
    pip install --no-cache-dir -U duckietown-shell && \
    cd .. && \
    rm -rf duckietown-shell

WORKDIR /root/.dt-shell/

CMD dts
