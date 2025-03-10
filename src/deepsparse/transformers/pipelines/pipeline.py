# Copyright (c) 2021 - present / Neuralmagic, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Base Pipeline class for transformers inference pipeline
"""


import warnings
from typing import Any, List, Mapping, Optional

import numpy
from transformers.models.auto import AutoConfig, AutoTokenizer

from deepsparse import Pipeline
from deepsparse.transformers.helpers import (
    get_onnx_path_and_configs,
    overwrite_transformer_onnx_model_inputs,
)


__all__ = [
    "TransformersPipeline",
    "pipeline",
]


class TransformersPipeline(Pipeline):
    """
    Base deepsparse.Pipeline class for transformers model loading. This class handles
    the parsing of deepsparse-transformers files and model inputs, supporting loading
    from sparsezoo, a directory containing a model.onnx, tokenizer, and model config,
    or just an ONNX file with the ability to load a tokenizer and model config from
    a default huggingface-transformers model.

    Note, when implementing child tasks in deepsparse.transformers.pipelines,
    in addition to registering task names with Pipeline.register, task names should
    be added to the supported nlp tasks in deepsparse.tasks so they can be properly
    imported at runtime.

    :param model_path: sparsezoo stub to a transformers model, an ONNX file, or
        (preferred) a directory containing a model.onnx, tokenizer config, and model
        config. If no tokenizer and/or model config(s) are found, then they will be
        loaded from huggingface transformers using the `default_model_name` key
    :param engine_type: inference engine to use. Currently supported values include
        'deepsparse' and 'onnxruntime'. Default is 'deepsparse'
    :param batch_size: static batch size to use for inference. Default is 1
    :param num_cores: number of CPU cores to allocate for inference engine. None
        specifies all available cores. Default is None
    :param scheduler: (deepsparse only) kind of scheduler to execute with.
        Pass None for the default
    :param input_shapes: list of shapes to set ONNX the inputs to. Pass None
        to use model as-is. Default is None
    :param alias: optional name to give this pipeline instance, useful when
        inferencing with multiple models. Default is None
    :param sequence_length: static sequence length to use for inference
    :param default_model_name: huggingface transformers model name to use to
        load a tokenizer and model config when none are provided in the `model_path`.
        Default is 'bert-base-uncased'
    """

    def __init__(
        self,
        *,
        sequence_length: int = 128,
        default_model_name: str = "bert-base-uncased",
        **kwargs,
    ):

        self._sequence_length = sequence_length
        self._default_model_name = default_model_name

        self.config = None
        self.tokenizer = None
        self.onnx_input_names = None

        self._temp_model_directory = None

        super().__init__(**kwargs)

    @property
    def sequence_length(self) -> int:
        """
        :return: static sequence length to use for inference
        """
        return self._sequence_length

    @property
    def default_model_name(self) -> str:
        """
        :return: huggingface transformers model name to use to
            load a tokenizer and model config when none are provided in the
            `model_path`
        """
        return self._default_model_name

    def setup_onnx_file_path(self) -> str:
        """
        Parses ONNX, tokenizer, and config file paths from the given `model_path`.
        Supports sparsezoo stubs. If a tokenizer and/or config file are not found,
        they will be defaulted to the default_model_name in the transformers repo

        :return: file path to the processed ONNX file for the engine to compile
        """
        onnx_path, config_path, tokenizer_path = get_onnx_path_and_configs(
            self.model_path
        )

        # default config + tokenizer if necessary
        config_path = config_path or self.default_model_name
        tokenizer_path = tokenizer_path or self.default_model_name

        self.config = AutoConfig.from_pretrained(
            config_path, finetuning_task=self.task if hasattr(self, "task") else None
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path, model_max_length=self.sequence_length
        )

        # overwrite onnx graph to given required input shape
        (
            onnx_path,
            self.onnx_input_names,
            self._temp_model_directory,
        ) = overwrite_transformer_onnx_model_inputs(
            onnx_path, max_length=self.sequence_length
        )

        return onnx_path

    def tokens_to_engine_input(
        self, tokens: Mapping[Any, numpy.ndarray]
    ) -> List[numpy.ndarray]:
        """
        :param tokens: outputs of the pipeline tokenizer
        :return: list of numpy arrays in expected order for model input
        """
        if not all(name in tokens for name in self.onnx_input_names):
            raise ValueError(
                f"pipeline expected arrays with names {self.onnx_input_names}, "
                f"received inputs: {list(tokens.keys())}"
            )

        return [tokens[name] for name in self.onnx_input_names]


def pipeline(
    task: str,
    model_name: Optional[str] = None,
    model_path: Optional[str] = None,
    engine_type: str = "deepsparse",
    config: Optional[str] = None,
    tokenizer: Optional[str] = None,
    max_length: int = 128,
    num_cores: Optional[int] = None,
    scheduler: Optional[str] = None,
    batch_size: Optional[int] = 1,
    **kwargs,
) -> Pipeline:
    """
    [DEPRECATED] - deepsparse.transformers.pipeline is deprecated to create DeepSparse
    pipelines for transformers tasks use deepsparse.Pipeline.create(task, ...)

    Utility factory method to build a Pipeline

    :param task: name of the task to define which pipeline to create. Currently,
        supported task - "question-answering"
    :param model_name: canonical name of the hugging face model this model is based on
    :param model_path: path to model directory containing `model.onnx`, `config.json`,
        and `tokenizer.json` files, ONNX model file, or SparseZoo stub
    :param engine_type: inference engine name to use. Options are 'deepsparse'
        and 'onnxruntime'. Default is 'deepsparse'
    :param config: huggingface model config, if none provided, default will be used
        which will be from the model name or sparsezoo stub if given for model path
    :param tokenizer: huggingface tokenizer, if none provided, default will be used
    :param max_length: maximum sequence length of model inputs. default is 128
    :param num_cores: number of CPU cores to run engine with. Default is the maximum
        available
    :param scheduler: The scheduler to use for the engine. Can be None, single or multi
    :param batch_size: The batch_size to use for the pipeline. Defaults to 1
        Note: `question-answering` pipeline only supports a batch_size of 1.
    :param kwargs: additional key word arguments for task specific pipeline constructor
    :return: Pipeline object for the given taks and model
    """
    warnings.warn(
        "[DEPRECATED] - deepsparse.transformers.pipeline is deprecated to create "
        "DeepSparse pipelines for transformers tasks use deepsparse.Pipeline.create()"
    )

    if config is not None or tokenizer is not None:
        raise ValueError(
            "Directly passing in a config or tokenizer to DeepSparse transformers "
            "pipelines is no longer supported. config and tokenizer objects should "
            "be specified by including config.json and tokenizer.json files in the "
            "model directory respectively"
        )

    return Pipeline.create(
        task=task,
        model_path=model_path,
        engine_type=engine_type,
        batch_size=batch_size,
        num_cores=num_cores,
        scheduler=scheduler,
        sequence_length=max_length,
        default_model_name=model_name,
        **kwargs,
    )
