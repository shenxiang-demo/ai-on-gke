# Use an official Envoy image as a base
FROM envoyproxy/envoy:v1.18.3

# Add your Wasm filter
COPY ../wasm_filter/target/wasm32-unknown-unknown/release/wasm_filter.wasm /etc/envoy/wasm_filter.wasm
#COPY ./wasm_filter/pkg/wasm_filter_bg.wasm /etc/envoy/wasm_filter.wasm
#COPY ./wasm_filter/pkg/wasm_filter.js /etc/envoy/wasm_filter.js 


# Copy the Envoy configuration file
COPY envoy.yaml /etc/envoy/envoy.yaml


RUN chmod 777 /etc/envoy/wasm_filter.wasm
RUN chmod 777 /etc/envoy/envoy.yaml
# Set the command to run Envoy
CMD ["envoy", "-c", "/etc/envoy/envoy.yaml"]
