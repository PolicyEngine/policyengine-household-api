FROM gcr.io/google-appengine/python
RUN pip install git+https://github.com/policyengine/policyengine-api-light
ENV GOOGLE_APPLICATION_CREDENTIALS .gac.json
ADD . /app
RUN cd /app && make install && make test
CMD ./start.sh
