FROM redis:5.0

LABEL maintainer="Ruslan Iakhin <ruslan.k.yakhin@gmail.com>"

RUN apt-get update; \
    apt-get install -y wget dnsutils

COPY etc/ /etc/

RUN chmod +x /etc/bootstrap-pod.sh

CMD [ "/etc/bootstrap-pod.sh" ]