ARG IMAGE=intersystems/iris-community:latest-em
FROM $IMAGE

ENV IRISINSTALLDIR "/usr/irissys"
ENV LD_LIBRARY_PATH "$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH"
ENV IRISUSERNAME "SuperUser"
ENV IRISPASSWORD "SYS"
ENV IRISNAMESPACE "ENSEMBLE"
ENV COMLIB "$IRISINSTALLDIR/bin"
ENV PYTHONPATH "$IRISINSTALLDIR/lib/python:$IRISINSTALLDIR/mgr/python"
ENV PATH "/usr/irissys/mgr/python/bin:/usr/irissys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/irisowner/bin:/home/irisowner/.local/bin"


WORKDIR /home/irisowner/dev
COPY . .

RUN python3 -m pip install -r requirements.txt --target /usr/irissys/mgr/python --upgrade


RUN --mount=type=bind,src=.,dst=. \
    iris start IRIS && \
    iris merge IRIS merge.cpf && \
    iris session iris < iris.script &&\
	intersystems_pyprod /home/irisowner/dev/src/healthcare-openfda-pyprod/openfda_adverse_events.py && \
    iris stop IRIS quietly safely
    