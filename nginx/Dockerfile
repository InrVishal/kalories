FROM nginx:alpine

# Install openssl to generate self-signed keys
RUN apk add --no-cache openssl

# Set up ssl directory
RUN mkdir -p /etc/nginx/ssl

# Generate a self-signed TLS certificate
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx.key \
    -out /etc/nginx/ssl/nginx.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/OU=Unit/CN=localhost"

# Copy configurations
COPY nginx.conf /etc/nginx/nginx.conf
