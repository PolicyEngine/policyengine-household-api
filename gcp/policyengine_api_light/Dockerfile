FROM anthvolk/policyengine-api-light:latest
ENV GOOGLE_APPLICATION_CREDENTIALS .gac.json
ENV AUTH0_ADDRESS_NO_DOMAIN .address
ENV AUTH0_AUDIENCE_NO_DOMAIN .audience
ADD . /app
RUN cd /app && make install && make test
CMD ./start.sh 
