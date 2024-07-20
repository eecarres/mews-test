# mews-test
This repository contains the code to solve the [proposed task](https://github.com/MewsSystems/tech-platform-engineering-interview-task) by Mews.

## Introduction
This repository contains code that analyzes a specific log file provided by Mews, using Normal Distribution for regresion detection on endpoints defined in the log file.

The app takes a chunk of log lines definining responses of an endpoint. The amount of lines is determined by how many fit in the `window_minutes` paraemter. It iterates through the chunks, comparing the current chunk mean value with the already calculated mean for the previous time blocks to see if it increased more than the threshold defined by the Z-score value. A [typical](https://docs.sentry.io/product/issues/issue-details/performance-issues/endpoint-regressions/) value, representing 95 percentile, is a Z score of 1.645.

So, assuming you have an endpoint with 100ms of mean duration, with 20 ms of standad deviation, this would mean that, using the default value (1.645) of the Z threshold, everything longer than 132.9 ms would be considered a regression.

## Notes
This repository is based on [pandas](https://pandas.pydata.org/), so basic knowledge of dataframes may be necessary (they're basically tables). The code is well documented though, so it should be easy to understand anyways.

## Assumptions
Several assumptions have been made in order to make this task easier (to keep it in the time cap):
- **The times are sorted** (this is very important, the algorithm is based on this).
- The 5 minute "window" has been assumed to be adequate, thus no exact time of failure search has been coded
- Endpoints start working nominally (there's no regression in the first minutes, so we can determine what "regular endpoint times" are)
- Keys and generally, structure of the file (lines of JSON) is fixed

Things NOT assumed by the code:
- Size of the log file: It's been designed for arbitrary size, although the amount of logs in the `window_minutes` needs to fit in memory. This could be solved if needed to be completely arbitrary. For example, we could set a maximum size of lines for the dataframe and generate means and other calculations per sub-interval and merge them.
- The data is ordered by endpoint: we do a search initially to gather all endpoints defined in the logs, just in case

- Due to time restrictions, some tasks have not been accomplished:
    - Lack of tests: I did not add any because the valuable ones would have required fake data that I had to create. I thought it was better spending time on other parts of the repo (like Dockerfile) and use the provided logs file for testing.
    - Lack of CICD: typically a quality stage, followed by docker image build and tests, no deployment in this case.
    

## Build and Run with Docker

1. **Build the Docker image:**
    Make sure you are in the root directory of the repository where the `Dockerfile` is located, then run:
    ```sh
    docker build -t log-analyzer .
    ```

2. **Run the Docker container:**
    To run the application using the built Docker image:
    ```sh
    docker run --rm -v $(pwd):/app log-analyzer log_analyzer logs.txt
    ```
