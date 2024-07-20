import math
from typing import Generator, Annotated

import pandas as pd
import typer
from rich.console import Console

# Create the typer app (CLI) to accept and parse the arguments
app = typer.Typer(no_args_is_help=True)

# Initialize the Console object for rich messages in the terminal
console = Console()

# Specific definitions for the logs.txt file (assumptions)
ENDPOINT_KEY = "Endpoint"
TIMESTAMP_KEY = "TimeStamp"
DURATION_KEY = "Duration"

INCORRECT_KEYS_IN_LOGS_ERROR = (
    f"It seems some key in the logs is different from expected. Expected are {ENDPOINT_KEY},{TIMESTAMP_KEY} and"
    f" {DURATION_KEY}"
)

# Defaults
DEFAULT_CHUNKSIZE = 10000
DEFAULT_WINDOW_MINUTES = 5
DEFAULT_Z_THRESHOLD = 1.645


# Notice that when only one app.command, you don't need to specify the name in the terminal call
@app.command()
def run_analysis(
    file_path: Annotated[str, typer.Argument(help="Path to the log file.")],
    z_threshold: Annotated[
        float,
        typer.Argument(help="The Z-score threshold for detecting outliers. Default value is " f"{DEFAULT_Z_THRESHOLD}"),
    ] = DEFAULT_Z_THRESHOLD,
    window_minutes: Annotated[
        int, typer.Argument(help=f"The minutes 'window' for the analysis. Default value is {DEFAULT_WINDOW_MINUTES}")
    ] = DEFAULT_WINDOW_MINUTES,
    chunksize: Annotated[
        int,
        typer.Argument(
            help="The number of rows taken each time of the file. The more, the faster, but a huge number could end up"
            f"in MemoryError. Default value is {DEFAULT_CHUNKSIZE}"
        ),
    ] = DEFAULT_CHUNKSIZE,
) -> None:
    """
    The app takes a chunk of log lines definining responses of an endpoint. The amount of lines is determined by how
    many fit in the `window_minutes`. It iterates through the chunks, comparing the current chunk mean value with
    the already calculated mean for the previous time blocks to see if it increased more than the threshold defined
    by the Z-score value.

    A typical value, representing 95 percentile, is a Z score of 1.645.

    So, assuming you have an endpoint with 100ms of mean duration, with 20 ms of standad deviation, this would mean
    that, using the default value (1.645) of the Z threshold, everything longer than 132.9 ms would be considered
    a regression.
    """
    # Get the values of the endpoints (in case they're not ordered)
    endpoints = get_unique_endpoints(file_path, chunksize=chunksize)

    for endpoint in endpoints:
        # Get the generator for the endpoint dataframe and analyze it
        dataframe_generator = get_dataframe_for_endpoint_in_intervals(
            file_path, endpoint, window_minutes=window_minutes, chunksize=chunksize
        )
        analyze_endpoint(endpoint, dataframe_generator, z_threshold)


def analyze_endpoint(endpoint: str, dataframe_generator: Generator, z_threshold: float):
    """
    Iterates through the time intervales in the dataframe containing the durations of the responses of the endpoint,
    calculates the mean of the chunk, and calculates it's Z-score based on the previous intervals. If the score is
    greater than the threshold, adds, to a list of regression start moments,  the moment in which the regression
    happened.

    Parameters
        endpoint (str): The name of the endpoint to analyze
        dataframe_generator (Generator): Generator that returns dataframes of the defined interval
        z_threshold (float): The maximum value of Z score of the interval. Anything higher will be considered regression

    Returns
        None
    """
    # Initialize endpoint variables
    endpoint_mean_duration = None
    endpoint_std_duration = None
    endpoint_samples = None
    endpoint_regression = False
    last_interval_was_regression = False
    endpoint_regression_list = []

    console.print(f" :magnifying_glass_tilted_right: Analyzing endpoint {endpoint}", style="bold", end=": ")

    # For each interval, we found if the endpoint has regressed. We assume it starts working properly, so first
    # interval is never on regression
    for interval_dataframe in dataframe_generator:
        # Get interval information
        try:
            interval_mean_duration = interval_dataframe[DURATION_KEY].mean()
            interval_std_duration = interval_dataframe[DURATION_KEY].std()
        except KeyError:
            console.print(INCORRECT_KEYS_IN_LOGS_ERROR)
            raise
        interval_samples = len(interval_dataframe)

        # For the first interval, we just set the endpoint values to be the same as the interval
        if endpoint_mean_duration is None:
            endpoint_mean_duration = interval_mean_duration
            endpoint_std_duration = interval_std_duration
            endpoint_samples = interval_samples

        else:
            try:
                z_score = (interval_mean_duration - endpoint_mean_duration) / endpoint_std_duration
            except ZeroDivisionError:
                # Almost impossible, would mean all endpoint responses took exactly same time
                if interval_mean_duration == endpoint_mean_duration:
                    z_score = 0
                else:
                    z_score = z_threshold + 1
            # If the score is higher than the threshold, it's considered a regression (outside of percentile)
            if z_score > z_threshold:
                endpoint_regression = True
                # Only add to list if it's a new regression, not a continuation of previous interval
                if not last_interval_was_regression:
                    try:
                        endpoint_regression_list.append(interval_dataframe.iloc[0][TIMESTAMP_KEY])
                    except KeyError:
                        console.print(INCORRECT_KEYS_IN_LOGS_ERROR)
                        raise
                last_interval_was_regression = True

            # If it's not, then we update the mean/std of the whole set of logs already analyzed
            else:
                endpoint_mean_duration = combined_mean(
                    endpoint_mean_duration, endpoint_samples, interval_mean_duration, interval_samples
                )                
                endpoint_std_duration = combined_standard_deviation(
                    endpoint_mean_duration,
                    endpoint_std_duration,
                    endpoint_samples,
                    interval_mean_duration,
                    interval_std_duration,
                    interval_samples,
                )
                endpoint_samples = endpoint_samples + interval_samples

    # Finish by printing the result
    if endpoint_regression:
        console.print(
            f"Found regression/s :bug: : Start times: {[r.isoformat() for r in endpoint_regression_list]}, amount of"
            f" regresions:{len(endpoint_regression_list)}",
            style="bold",
        )
    else:
        console.print("No regressions found! :tada:", style="bold")


def get_unique_endpoints(file_path: str, chunksize: int = DEFAULT_CHUNKSIZE) -> set:
    """
    Read a JSON-lines file in chunks and get all unique values of the endpoint column.

    Parameters:
        file_path (str): Path to the JSON file.
        chunksize (int): Number of lines per chunk. Default is DEFAULT_CHUNKSIZE.

    Returns:
        set: A set of unique values from the endpoint column.
    """
    # A set contains unindexed,unordered and unique elements
    unique_endpoints = set()

    # Read the file in chunks. lines=True is for reading a file where every line is a JSON
    for chunk in pd.read_json(file_path, lines=True, chunksize=chunksize):
        # Update the set of unique endpoints
        try:
            unique_endpoints.update(chunk[ENDPOINT_KEY].unique())
        except KeyError:
            console.print(INCORRECT_KEYS_IN_LOGS_ERROR)
            raise

    return unique_endpoints


def get_dataframe_for_endpoint_in_intervals(
    file_path: str,
    endpoint_value: str,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    chunksize: int = DEFAULT_CHUNKSIZE,
) -> Generator[pd.DataFrame, None, None]:
    """
    Read JSON-lines file in chunks and yield DataFrames with rows for the specified endpoint
    in defined intervals.

    Parameters:
        file_path (str): Path to the JSON file.
        endpoint_value (str): The value of the 'Endpoint' to filter by.
        window_minutes (int): The time interval for each yielded DataFrame (default is 'DEFAULT_WINDOW_MINUTES').
        chunksize (int): Number of lines per chunk. Default is DEFAULT_CHUNKSIZE.

    Yields:
        pd.DataFrame: A DataFrame containing rows with the specified 'Endpoint' value within each interval.
    """
    buffer = pd.DataFrame()
    interval_start = None

    # Read the file in chunks. lines=True is for reading a file where every line is a JSON
    for chunk in pd.read_json(file_path, lines=True, chunksize=chunksize):
        # Filter the chunk for the specified endpoint value
        try:
            chunk = chunk[chunk[ENDPOINT_KEY] == endpoint_value]
            # Convert the 'TimeStamp' column to datetime
            chunk[TIMESTAMP_KEY] = pd.to_datetime(chunk[TIMESTAMP_KEY])
        except KeyError:
            console.print(INCORRECT_KEYS_IN_LOGS_ERROR)
            raise

        while not chunk.empty:

            # If it's the first chunk, get the start timestamp
            if interval_start is None:
                interval_start = chunk.iloc[0][TIMESTAMP_KEY]
            # Set the interval end (for all iterations)
            interval_end = interval_start + pd.Timedelta(minutes=window_minutes)

            # Generate a mask of the chunk for filtering data inside the interval
            mask = (chunk[TIMESTAMP_KEY] >= interval_start) & (chunk[TIMESTAMP_KEY] < interval_end)

            # Apply the mask to the chunk, effectively splitting the chunk into the interval_data and the rest
            interval_data = chunk[mask]
            chunk = chunk[~mask]

            # Add the interval data to the buffer
            buffer = pd.concat([buffer, interval_data])

            # If there is interval data, it's yielded if complete, or waits till the next chunk to be yielded completely
            if not interval_data.empty:

                # We need to check if interval is full: If chunk has still information, it means interval is completed,
                # so we can yield it, and then update the timestamps so the next iteration feeds the next interval
                if not chunk.empty:
                    yield buffer
                    # Empty the buffer
                    buffer = pd.DataFrame()
                    # Set the new start of the interval (the end is defined some lines earlier)
                    interval_start = interval_end

                # If the chunk is empty, we may be leaving data for the interval that's on the next chunk, so we need
                # to get out of the while to gather a new chunk, but without changing the interval datetimes
                else:
                    break

            # Corner case: the end of the chunk and the end of the interval happen at the same time
            else:
                # Chunk can't be empty, so it means it has data of the next interval, so we need to yield the buffer
                # and start the next interval
                yield buffer
                buffer = pd.DataFrame()
                interval_start = interval_end

    # After processing all chunks, yield any remaining rows as the last interval's DataFrame
    if not buffer.empty:
        yield buffer


def combined_mean(mean1: float, n1: int, mean2: float, n2: int) -> float:
    """
    Calculate the combined mean of two datasets:
    https://www.geeksforgeeks.org/combined-mean-formula-and-examples/

    Parameters:
        mean1 (float): Mean of the first dataset.
        n1 (int): Number of observations in the first dataset.
        mean2 (float): Mean of the second dataset.
        n2 (int): Number of observations in the second dataset.

    Returns:
        float: The combined mean of the two datasets.
    """
    # Calculate the sum of observations in both datasets
    total_sum = (mean1 * n1) + (mean2 * n2)

    # Calculate the combined mean
    combined_mean = total_sum / (n1 + n2)

    return combined_mean


def combined_standard_deviation(
    mean1: float, std_dev1: float, n1: int, mean2: float, std_dev2: float, n2: int
) -> float:
    """
    Calculate the combined standard deviation of two datasets:
    https://www.geeksforgeeks.org/combined-standard-deviation-meaning-formula-and-example/

    Parameters:
        mean1 (float): Mean of the first dataset.
        std_dev1 (float): Standard deviation of the first dataset.
        n1 (int): Number of observations in the first dataset.
        mean2 (float): Mean of the second dataset.
        std_dev2 (float): Standard deviation of the second dataset.
        n2 (int): Number of observations in the second dataset.

    Returns:
        float: The combined standard deviation of the two datasets.
    """
    # Calculate the combined mean
    combined_mean_value = combined_mean(mean1, n1, mean2, n2)

    # Calculate the sum of squared deviations for each dataset
    sum_squared_dev1 = (std_dev1**2 + (mean1 - combined_mean_value) ** 2) * n1
    sum_squared_dev2 = (std_dev2**2 + (mean2 - combined_mean_value) ** 2) * n2

    # Calculate the combined variance
    combined_variance = (sum_squared_dev1 + sum_squared_dev2) / (n1 + n2)

    # Calculate the combined standard deviation
    combined_std_dev = math.sqrt(combined_variance)

    return combined_std_dev


if __name__ == "__main__":
    app()
