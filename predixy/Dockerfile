FROM ubuntu:18.04

LABEL maintainer="Ruslan Iakhin <ruslan.k.yakhin@gmail.com>"

ENV VERSION 1.0.5
ENV WORKDIR /root/predixy

WORKDIR $WORKDIR

COPY . $WORKDIR

RUN apt-get update; \
    apt-get upgrade -y; \
    apt-get install -y build-essential

RUN make debug; \
    mv src/predixy /usr/local/bin; \
    cp -r conf /etc/

CMD ["/usr/local/bin/predixy", "/etc/conf/predixy.conf"]