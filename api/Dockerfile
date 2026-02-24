# Use the official Azure Functions Node.js base image
FROM mcr.microsoft.com/azure-functions/node:4-node22

# Set environment variables
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    DEBIAN_FRONTEND=noninteractive

# Install LibreOffice - split into multiple steps for better error handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-java-common && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /home/site/wwwroot

# Copy package files
COPY package*.json ./

# Install npm dependencies
RUN npm install --production

# Copy function app code
COPY . .

# Expose port 80 for Azure
EXPOSE 80

# Start the Azure Functions host
CMD ["/azure-functions-host/Microsoft.Azure.WebJobs.Script.WebHost"]
