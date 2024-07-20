# Use the Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
# We extend path so it covers the path were the python app will be installed
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Create a non-root user and group
RUN addgroup --gid 1001 appgroup && \
    adduser --uid 1001 --ingroup appgroup --shell /bin/sh --disabled-password appuser

RUN export PATH=${PATH}:/home/appuser/.local/bin

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Change ownership of the /app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Install the required dependencies
RUN pip install -e .

# Command to run the application
CMD ["log_analyzer"]
