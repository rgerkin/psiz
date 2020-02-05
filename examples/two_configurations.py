# -*- coding: utf-8 -*-
# Copyright 2020 The PsiZ Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Example that infers an embedding from two trial configurations.

Fake data is generated from a ground truth model for two different
trial configurations: 2-choose-1 and 8-choose-2. This example
demonstrates how one can use data collected in a variety of formats to
infer a single embedding.
"""

import numpy as np

from psiz.trials import stack
from psiz.models import Exponential
from psiz.simulate import Agent
from psiz.generator import RandomGenerator
from psiz.utils import similarity_matrix, matrix_comparison


def main():
    """Run the simulation that infers an embedding for three groups."""
    # Settings.
    n_stimuli = 25
    n_dim = 3
    n_restart = 3  # 20

    # Ground truth embedding.
    emb_true = ground_truth(n_stimuli, n_dim)

    # Generate a random docket of trials using two different trial
    # configurations.
    # Generate 1000 2-choose-1 trials.
    n_reference = 2
    n_select = 1
    gen_2c1 = RandomGenerator(n_reference, n_select)
    n_trial = 1000
    docket_2c1 = gen_2c1.generate(n_trial, n_stimuli)
    # Generate 1000 8-choose-2 trials.
    n_reference = 8
    n_select = 2
    gen_8c2 = RandomGenerator(n_reference, n_select)
    n_trial = 1000
    docket_8c2 = gen_8c2.generate(n_trial, n_stimuli)
    # Merge both sets of trials into a single docket.
    docket = stack([docket_2c1, docket_8c2])

    # Simulate similarity judgments for the three groups.
    agent = Agent(emb_true)
    obs = agent.simulate(docket)

    # Infer embedding.
    emb_inferred = Exponential(n_stimuli, n_dim)
    emb_inferred.fit(obs, n_restart, verbose=1)

    # Compare the inferred model with ground truth by comparing the
    # similarity matrices implied by each model.
    simmat_truth = similarity_matrix(emb_true.similarity, emb_true.z)
    simmat_infer = similarity_matrix(emb_inferred.similarity, emb_inferred.z)
    r_squared = matrix_comparison(simmat_truth, simmat_infer, score='r2')

    # Display comparison results. A good inferred model will have a high
    # R^2 value on the diagonal elements (max is 1) and relatively low R^2
    # values on the off-diagonal elements.
    print(
        '\n    R^2 Model Comparison: {0: >6.2f}\n'.format(r_squared)
    )


def ground_truth(n_stimuli, n_dim):
    """Return a ground truth embedding."""
    emb = Exponential(
        n_stimuli, n_dim=n_dim)
    mean = np.ones((n_dim))
    cov = .03 * np.identity(n_dim)
    z = np.random.multivariate_normal(mean, cov, (n_stimuli))
    emb.z = z
    emb.rho = 2
    emb.tau = 1
    emb.beta = 10
    emb.gamma = 0.001
    emb.trainable("freeze")
    return emb


if __name__ == "__main__":
    main()