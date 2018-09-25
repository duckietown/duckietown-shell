FROM resin/raspberry-pi-alpine-python:2

RUN [ "cross-build-start" ]

COPY . duckietown-shell

RUN apk add --no-cache git

RUN cd duckietown-shell && \
    pip install python-dateutil && \
    pip install --no-cache-dir -U duckietown-shell && \
    cd .. && \
    rm -rf duckietown-shell

RUN [ "cross-build-end" ]

CMD dts
