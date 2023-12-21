FROM policyengine/policyengine-api-light:latest
ENV GOOGLE_APPLICATION_CREDENTIALS .gac.json
ADD . /app
RUN cd /app && make install && make test
CMD ./start.sh 
