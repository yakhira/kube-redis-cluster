FROM redis:alpine
MAINTAINER "Ruslan Iakhin <ruslan.iakhin@concur.com>"

ENV WORKDIR /usr/src/app
WORKDIR $WORKDIR

COPY . $WORKDIR/

RUN mkdir -p /var/lib/redis; \
    mkdir -p $WORKDIR/logs
RUN apk --no-cache update; \
    apk --no-cache add python3 git supervisor gcc python3-dev musl-dev py-twisted
RUN pip3 install click requests twisted; \
    git clone https://github.com/yakhira/redis-py.git; \
    cd redis-py; \
    python3 setup.py install; \
    rm -rf $WORKDIR/redis-py

EXPOSE 6379 16379
CMD ["/usr/bin/supervisord", "-c", "conf/supervisord.conf"]