FROM policyengine/policyengine-household-api:latest

ENV GOOGLE_APPLICATION_CREDENTIALS .gac.json
ENV AUTH0_ADDRESS_NO_DOMAIN .address
ENV AUTH0_AUDIENCE_NO_DOMAIN .audience
ENV AUTH0_TEST_TOKEN_NO_DOMAIN .test-token
ENV USER_ANALYTICS_DB_USERNAME .dbuser
ENV USER_ANALYTICS_DB_PASSWORD .dbpw
ENV USER_ANALYTICS_DB_CONNECTION_NAME .dbconn
ENV ANTHROPIC_API_KEY .anthropic

WORKDIR /app

# Copy application
ADD . /app

# Make start.sh executable
RUN chmod +x /app/start.sh

RUN cd /app && make install && make test

# Use full path to start.sh
CMD ["/bin/sh", "/app/start.sh"]