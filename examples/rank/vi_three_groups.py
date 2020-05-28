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

"""Example that infers a shared embedding for three groups.

Fake data is generated from a ground truth model for three different
groups. In this example, these groups represent groups of agents with
varying levels of skill: novices, intermediates, and experts. Each group
has a different set of attention weights. An embedding model is
inferred from the simulated data and compared to the ground truth
model.

Example output:
    Attention weights:
          Novice | [3.38 3.32 0.49 0.43]
    Intermediate | [2.06 2.18 2.04 2.18]
          Expert | [0.55 0.50 3.40 3.32]

    Model Comparison (R^2)
    ================================
      True  |        Inferred
            | Novice  Interm  Expert
    --------+-----------------------
     Novice |   0.95    0.68    0.16
     Interm |   0.64    0.96    0.54
     Expert |   0.16    0.61    0.96

"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import StratifiedKFold
import tensorflow as tf
import tensorflow_probability as tfp

import psiz

# Uncomment the following line to force eager execution.
# tf.config.experimental_run_functions_eagerly(True)


def main():
    """Run the simulation that infers an embedding for three groups."""
    # Settings.
    n_stimuli = 30
    n_dim = 4
    n_group = 3
    n_restart = 1
    batch_size = 200

    emb_true = ground_truth(n_stimuli, n_dim, n_group)

    # Generate a random docket of trials to show each group.
    n_trial = 2000
    n_reference = 8
    n_select = 2
    generator = psiz.generator.RandomGenerator(
        n_stimuli, n_reference=n_reference, n_select=n_select
    )
    docket = generator.generate(n_trial)

    # Create virtual agents for each group.
    agent_novice = psiz.generator.Agent(emb_true, group_id=0)
    agent_interm = psiz.generator.Agent(emb_true, group_id=1)
    agent_expert = psiz.generator.Agent(emb_true, group_id=2)

    # Simulate similarity judgments for each group.
    obs_novice = agent_novice.simulate(docket)
    obs_interm = agent_interm.simulate(docket)
    obs_expert = agent_expert.simulate(docket)
    obs_all = psiz.trials.stack((obs_novice, obs_interm, obs_expert))

    # Partition observations into train and validation set.
    skf = StratifiedKFold(n_splits=10)
    (train_idx, val_idx) = list(
        skf.split(obs_all.stimulus_set, obs_all.config_idx)
    )[0]
    obs_train = obs_all.subset(train_idx)
    obs_val = obs_all.subset(val_idx)

    # Use early stopping.
    cb_early = psiz.keras.callbacks.EarlyStoppingRe(
        'val_cce', patience=15, mode='min', restore_best_weights=True
    )
    callbacks = [cb_early]

    compile_kwargs = {
        'loss': tf.keras.losses.CategoricalCrossentropy(),
        'optimizer': tf.keras.optimizers.Adam(lr=.001),
        'weighted_metrics': [
            tf.keras.metrics.CategoricalCrossentropy(name='cce')
        ]
    }

    # Define model with a shared embedding and group-specific attention
    # weights.
    embedding = tf.keras.layers.Embedding(
        n_stimuli+1, n_dim, mask_zero=True
    )
    kernel = psiz.keras.layers.AttentionKernel(
        distance=psiz.keras.layers.WeightedMinkowskiVariational(),
        attention=psiz.keras.layers.GroupAttentionVariational(
            n_dim=n_dim, n_group=n_group
        ),
        similarity=psiz.keras.layers.ExponentialSimilarityVariational()
    )
    model = psiz.models.Rank(
        embedding=embedding, kernel=kernel, n_sample_test=100
    )
    emb_inferred = psiz.models.Proxy(model=model)
    # Infer model.
    restart_record = emb_inferred.fit(
        obs_train, validation_data=obs_val, epochs=1000, batch_size=batch_size,
        callbacks=callbacks, monitor='val_cce', n_restart=n_restart, verbose=2,
        compile_kwargs=compile_kwargs
    )

    # Compare the inferred model with ground truth by comparing the
    # similarity matrices implied by each model.
    def truth_sim_func0(z_q, z_ref):
        return emb_true.similarity(z_q, z_ref, group_id=0)

    def truth_sim_func1(z_q, z_ref):
        return emb_true.similarity(z_q, z_ref, group_id=1)

    def truth_sim_func2(z_q, z_ref):
        return emb_true.similarity(z_q, z_ref, group_id=2)

    simmat_truth = (
        psiz.utils.pairwise_matrix(truth_sim_func0, emb_true.z),
        psiz.utils.pairwise_matrix(truth_sim_func1, emb_true.z),
        psiz.utils.pairwise_matrix(truth_sim_func2, emb_true.z)
    )

    def infer_sim_func0(z_q, z_ref):
        return emb_inferred.similarity(z_q, z_ref, group_id=0)

    def infer_sim_func1(z_q, z_ref):
        return emb_inferred.similarity(z_q, z_ref, group_id=1)

    def infer_sim_func2(z_q, z_ref):
        return emb_inferred.similarity(z_q, z_ref, group_id=2)

    simmat_infer = (
        psiz.utils.pairwise_matrix(infer_sim_func0, emb_inferred.z),
        psiz.utils.pairwise_matrix(infer_sim_func1, emb_inferred.z),
        psiz.utils.pairwise_matrix(infer_sim_func2, emb_inferred.z)
    )
    r_squared = np.empty((n_group, n_group))
    for i_truth in range(n_group):
        for j_infer in range(n_group):
            r_squared[i_truth, j_infer] = psiz.utils.matrix_comparison(
                simmat_truth[i_truth], simmat_infer[j_infer],
                score='r2'
            )

    # Display attention weights.
    # Permute inferred dimensions to best match ground truth.
    idx_sorted = np.argsort(-emb_inferred.w[0, :])
    attention_weight = emb_inferred.w[:, idx_sorted]
    group_labels = ["Novice", "Intermediate", "Expert"]
    print("\n    Attention weights:")
    for i_group in range(emb_inferred.n_group):
        print("    {0:>12} | {1}".format(
            group_labels[i_group],
            np.array2string(
                attention_weight[i_group, :],
                formatter={'float_kind': lambda x: "%.2f" % x})
            )
        )

    # Display comparison results. A good inferred model will have a high
    # R^2 value on the diagonal elements (max is 1) and relatively low R^2
    # values on the off-diagonal elements.
    print('\n    Model Comparison (R^2)')
    print('    ================================')
    print('      True  |        Inferred')
    print('            | Novice  Interm  Expert')
    print('    --------+-----------------------')
    print('     Novice | {0: >6.2f}  {1: >6.2f}  {2: >6.2f}'.format(
        r_squared[0, 0], r_squared[0, 1], r_squared[0, 2]))
    print('     Interm | {0: >6.2f}  {1: >6.2f}  {2: >6.2f}'.format(
        r_squared[1, 0], r_squared[1, 1], r_squared[1, 2]))
    print('     Expert | {0: >6.2f}  {1: >6.2f}  {2: >6.2f}'.format(
        r_squared[2, 0], r_squared[2, 1], r_squared[2, 2]))
    print('\n')

    # idx_sorted = np.array([0, 1, 2, 3])
    plot_posteriors(emb_inferred.model, idx_sorted)


def ground_truth(n_stimuli, n_dim, n_group):
    """Return a ground truth embedding."""
    embedding = tf.keras.layers.Embedding(
        n_stimuli+1, n_dim, mask_zero=True,
        embeddings_initializer=tf.keras.initializers.RandomNormal(stddev=.17)
    )
    kernel = psiz.keras.layers.AttentionKernel(
        attention=psiz.keras.layers.GroupAttention(
            n_dim=n_dim, n_group=n_group
        ),
        similarity=psiz.keras.layers.ExponentialSimilarity()
    )
    model = psiz.models.Rank(embedding=embedding, kernel=kernel)
    emb = psiz.models.Proxy(model=model)

    emb.w = np.array((
        (1.8, 1.8, .2, .2),
        (1., 1., 1., 1.),
        (.2, .2, 1.8, 1.8)
    ))
    emb.theta = {
        'rho': 2.,
        'tau': 1.,
        'beta': 10.,
        'gamma': 0.001
    }
    return emb


def plot_posteriors(model, idx_sorted):
    """Plot posteriors."""
    n_group = model.n_group
    n_dim = model.n_dim

    xg = np.linspace(0, 1, 1000)

    fig, ax = plt.subplots(figsize=(12, 5))

    subplot_counter = 1
    for i_group in range(n_group):
        for i_dim in range(n_dim):
            ax = plt.subplot(n_group, n_dim, subplot_counter)
            curr_dim = idx_sorted[i_dim]
            loc = model.kernel.attention.w_posterior.distribution.loc[i_group, curr_dim]
            scale = model.kernel.attention.w_posterior.distribution.scale[i_group, curr_dim]
            y = tfp.distributions.Normal(loc=loc, scale=scale).prob(xg)
            w_map = loc.numpy()
            ax.plot(xg, y)
            ax.text(loc, np.max(y), '{0:.2f}'.format(loc))
            ax.set_xlabel('w_{0}'.format(curr_dim))
            ax.set_ylabel('p(w_{0})'.format(curr_dim))
            # ax.set_title('Posterior')

            subplot_counter += 1

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
