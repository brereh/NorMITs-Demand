# -*- coding: utf-8 -*-
"""
Created on: Mon June 08:12:21 2021
Updated on:

Original author: Ben Taylor
Last update made by:
Other updates made by:

File purpose:
Collection of utility functions specifically for manipulating pandas
"""
# Builtins
import functools

from typing import List
from typing import Generator

# Third Party
import pandas as pd

# Local


def reindex_cols(df: pd.DataFrame,
                 columns: List[str],
                 throw_error: bool = True,
                 **kwargs,
                 ) -> pd.DataFrame:
    """
    Wrapper around df.reindex. Will throw error if columns aren't in df

    Parameters
    ----------
    df:
        THe pandas.DataFrame that should be reindexed

    columns:
        The columns to reindex df to.

    throw_error:
        Whether to throw and error or not if the given columns don't exist in
        df. If False, then operates exactly like calling df.reindex directly.

    kwargs:
        Any extra arguments to pass into df.reindex

    Returns
    -------
    reindexed_df:
        The given df, reindexed to only have columns as column names.

    Raises
    ------
    ValueError:
        If any of the given columns don't exists within df and throw_error is
        True.
    """
    if throw_error:
        # Check that all columns actually exist in df
        for col in columns:
            if col not in df:
                raise ValueError(
                    "No columns named '%s' in the given dataframe.\n"
                    "Only found the following columns: %s"
                    % (col, list(df))
                )

    return df.reindex(columns=columns, **kwargs)


def str_join_cols(df: pd.DataFrame,
                  columns: List[str],
                  separator: str = '_',
                  ) -> pd.Series:
    """
    Equivalent to separator.join(columns) for all rows of df

    Joins the given columns together using separator. Returns a pandas Series
    with the return value in.

    Parameters
    ----------
    df:
        The dataframe containing the columns to join

    columns:
        The columns in df to concatenate together

    separator:
        The separator to use when joining columns together.

    Returns
    -------
    joined_column:
        a Pandas.Series containing all columns joined together using separator
    """
    # Define the accumulator function
    def reducer(accumulator, item):
        return accumulator + separator + item

    # Join the cols together
    join_cols = [df[x].astype(str) for x in columns]
    return functools.reduce(reducer, join_cols)


def chunk_df(df: pd.DataFrame,
             chunk_size: int,
             ) -> Generator[pd.DataFrame, None, None]:
    """
    Yields chunk_size chunks of df

    Parameters
    ----------
    df:
        the pandas.DataFrame to chunk.

    chunk_size:
        The size of the chunks to use, in terms of rows.

    Yields
    ------
    df_chunk:
        A chunk of the given df of size chunk_size

    """
    for i in range(0, len(df), chunk_size):
        chunk_end = i + chunk_size
        yield df[i:chunk_end]
