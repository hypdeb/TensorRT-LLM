import json
import math
import os
import random
from typing import Generator, List

import numpy as np
from pydantic import BaseModel
from tokenizers import Tokenizer


class Sample(BaseModel):
    input_len: int
    input_ids: List[int]
    output_len: int
    task_id: int


class Workload(BaseModel):
    metadata: dict
    samples: List[Sample] = []

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.setup_workload_name()

    def setup_workload_name(self):
        # Keys to ignore
        ignore_keys = ["tokenizer"]
        # Create a string by concatenating keys and values with "__"
        workload_name = "__".join(f"{key}:{value}"
                                  for key, value in self.metadata.items()
                                  if key not in ignore_keys)
        self.metadata.setdefault("workload_name", workload_name)


def dataset_dump(
    input_lens: list[int],
    input_ids: list[list[int]],
    output_lens: list[int],
    task_ids: list[int],
    metadata: dict,
    output_file: str,
    output_format: str,
) -> None:
    if os.path.dirname(output_file) != "":
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
    match output_format:
        case "trtllm-bench":
            with open(output_file, "w") as f:
                for line in generate_dataset_as_json_lines(
                        input_ids, output_lens):
                    f.write(line + "\n")
        case "gptManagerBenchmark":
            samples = []
            for i in range(len(input_ids)):
                samples.append(
                    Sample(
                        input_len=input_lens[i],
                        input_ids=input_ids[i],
                        output_len=output_lens[i],
                        task_id=task_ids[i],
                    ))
            workload = Workload(metadata=metadata, samples=samples)
            with open(output_file, "w") as f:
                json.dump(workload.model_dump(), f)
        case _:
            raise ValueError(f"Unsupported output format: {output_format}")


def generate_dataset_as_json_lines(
        input_ids: list[list[int]],
        output_lens: list[int]) -> Generator[str, None, None]:
    for i, input_tokens in enumerate(input_ids):
        d = {
            "task_id": i,
            "input_ids": input_tokens,
            "output_tokens": output_lens[i]
        }
        yield json.dumps(d, separators=(",", ":"), ensure_ascii=False)


def print_dataset(input_ids: list[list[int]], output_lens: list[int]):
    for line in generate_dataset_as_json_lines(input_ids, output_lens):
        print(line)


def get_list_of_delays(delay_dist: str, mean_time_bet_reqs: float,
                       num_reqs: int, random_seed: int) -> list[float]:
    if delay_dist == "constant":
        delays = [mean_time_bet_reqs] * num_reqs
    elif delay_dist == "exponential_dist":
        delays = get_exponential_dist_delays(mean_time_bet_reqs, num_reqs,
                                             random_seed)

    return delays


def get_exponential_dist_delays(mean_time_bet_reqs: float, num_reqs: int,
                                random_seed: int) -> list[float]:
    # set seed for determinism
    np.random.seed(random_seed)
    return np.random.exponential(mean_time_bet_reqs, num_reqs).tolist()


def get_norm_dist_lengths(mean: float, stdev: float, num_reqs: int,
                          random_seed: int) -> list[int]:
    # set seed for determinism
    np.random.seed(random_seed)
    numbers_list = np.random.normal(loc=mean, scale=stdev,
                                    size=num_reqs).tolist()
    return [max(1, math.ceil(x)) for x in numbers_list]


def get_unif_dist_lengths(min_len: int, max_len: int, num_reqs: int,
                          random_seed: int) -> list[int]:
    # set seed for determinism
    rng = np.random.default_rng(random_seed)
    numbers = rng.integers(low=min_len, high=max_len + 1, size=num_reqs)
    return numbers.tolist()


def gen_random_tokens(ip_lens: list[int], tokenizer: Tokenizer,
                      random_seed: int) -> list[list[int]]:

    def get_sample_from_population(population_range, sample_size):
        # random.sample can not sample a value more than once. hence the check
        if sample_size < len(population_range):
            sample = random.sample(population_range, sample_size)
        else:
            sample = random.choices(population_range, k=sample_size)

        return sample

    input_ids = []
    random.seed(random_seed)
    for ip_len in ip_lens:
        start_ids = get_sample_from_population(range(0, tokenizer.vocab_size),
                                               ip_len)
        # Make sure it does not contain EOS token
        eos_id = tokenizer.encode(tokenizer.eos_token, add_special_tokens=False)
        while set(eos_id).issubset(start_ids):
            tmp_id = (eos_id[0] + 1) % tokenizer.vocab_size
            start_ids = [
                tmp_id if element == eos_id[0] else element
                for element in start_ids
            ]
        input_ids.append(start_ids)

    return input_ids
