## baseline: Neural Graph Collaborative Filtering (NGCF)
## XiangWang, Xiangnan He, MengWang, Fuli Feng, and Tat-Seng Chua. 2019. Neural Graph Collaborative Filtering. In Proceedings of the 42nd International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR ’19), 2019.

import tensorflow as tf
import numpy as np

class model_NGCF(object):
    def __init__(self, layer, graph, n_users, n_items, emb_dim, lr, lamda, optimization, pre_train_latent_factor, if_pretrain):
        self.model_name = 'NGCF'
        self.graph = graph
        self.n_users = n_users
        self.n_items = n_items
        self.emb_dim = emb_dim
        self.layer = layer
        self.lamda = lamda
        self.lr = lr
        self.optimization = optimization
        [self.U, self.V] = pre_train_latent_factor
        self.if_pretrain = if_pretrain

        self.A = self.adjacient_matrix()
        self.D = self.degree_matrix()
        self.R = self.random_walk()
        self.A_hat = self.dense_to_sparse(self.R)

        # placeholder definition
        self.users = tf.placeholder(tf.int32, shape=(None,))
        self.pos_items = tf.placeholder(tf.int32, shape=(None,))
        self.neg_items = tf.placeholder(tf.int32, shape=(None,))
        self.keep_prob = tf.placeholder(tf.float32, shape=(None))

        if self.if_pretrain:
            self.user_embeddings = tf.Variable(self.U, name='user_embeddings')
            self.item_embeddings = tf.Variable(self.V, name='item_embeddings')
        else:
            self.user_embeddings = tf.Variable(
                tf.random_normal([self.n_users, self.emb_dim], mean=0.01, stddev=0.02, dtype=tf.float32),
                name='user_embeddings')
            self.item_embeddings = tf.Variable(
                tf.random_normal([self.n_items, self.emb_dim], mean=0.01, stddev=0.02, dtype=tf.float32),
                name='item_embeddings')

        self.filters_1 = []
        self.filters_2 = []
        for k in range(self.layer):
            self.filters_1.append(
                tf.Variable((np.random.normal(0, 0.001, (self.emb_dim, self.emb_dim)) + np.diag(np.random.normal(1, 0.001, self.emb_dim))).astype(np.float32))
            )
            self.filters_2.append(
                tf.Variable((np.random.normal(0, 0.001, (self.emb_dim, self.emb_dim)) + np.diag(np.random.normal(1, 0.001, self.emb_dim))).astype(np.float32))
            )
#         self.A_hat = tf.nn.dropout(self.A_hat, self.keep_prob[1])  ## cannot dropout for sparse variables
        embeddings = tf.concat([self.user_embeddings, self.item_embeddings], axis=0)
        all_embeddings = [embeddings]
        for k in range(0, self.layer):
            propagations = tf.sparse_tensor_dense_matmul(self.A_hat, embeddings)
            embeddings_1 = propagations + embeddings
            embeddings_2 = tf.multiply(propagations, embeddings)
            embeddings = tf.nn.sigmoid(tf.matmul(embeddings_1, self.filters_1[k]) + tf.matmul(embeddings_2, self.filters_2[k]))
#             embeddings = tf.nn.relu(tf.matmul(embeddings_1, self.filters_1[k]) + tf.matmul(embeddings_2, self.filters_2[k]))
            all_embeddings += [embeddings]
        all_embeddings = tf.concat(all_embeddings, 1)
        self.user_all_embeddings, self.item_all_embeddings = tf.split(all_embeddings, [self.n_users, self.n_items], 0)

        self.u_embeddings = tf.nn.embedding_lookup(self.user_all_embeddings, self.users)
        self.pos_i_embeddings = tf.nn.embedding_lookup(self.item_all_embeddings, self.pos_items)
        self.neg_i_embeddings = tf.nn.embedding_lookup(self.item_all_embeddings, self.neg_items)
        self.u_embeddings_drop = tf.nn.dropout(self.u_embeddings, self.keep_prob[0])
        self.pos_i_embeddings_drop = tf.nn.dropout(self.pos_i_embeddings, self.keep_prob[0])
        self.neg_i_embeddings_drop = tf.nn.dropout(self.neg_i_embeddings, self.keep_prob[0])

        self.all_ratings = tf.matmul(self.u_embeddings, self.item_all_embeddings, transpose_a=False, transpose_b=True)

        self.u_embeddings_loss = tf.nn.embedding_lookup(self.user_embeddings, self.users)
        self.pos_i_embeddings_loss = tf.nn.embedding_lookup(self.item_embeddings, self.pos_items)
        self.neg_i_embeddings_loss = tf.nn.embedding_lookup(self.item_embeddings, self.neg_items)

        self.loss = self.create_bpr_loss(self.u_embeddings_drop, self.pos_i_embeddings_drop, self.neg_i_embeddings_drop) + \
                    self.lamda * self.regularization(self.u_embeddings_loss, self.pos_i_embeddings_loss,
                                                     self.neg_i_embeddings_loss, self.filters_1, self.filters_2)       

        if self.optimization == 'SGD':
            self.opt = tf.train.GradientDescentOptimizer(learning_rate=self.lr)
        if self.optimization == 'RMSProp':
            self.opt = tf.train.RMSPropOptimizer(learning_rate=self.lr)
        if self.optimization == 'Adam':
            self.opt = tf.train.AdamOptimizer(learning_rate=self.lr)
        if self.optimization == 'Adagrad':
            self.opt = tf.train.AdagradOptimizer(learning_rate=self.lr)

        self.updates = self.opt.minimize(self.loss, var_list=[self.user_embeddings, self.item_embeddings] + self.filters_1 + self.filters_2)

    def create_bpr_loss(self, users, pos_items, neg_items):
        pos_scores = tf.reduce_sum(tf.multiply(users, pos_items), axis=1)
        neg_scores = tf.reduce_sum(tf.multiply(users, neg_items), axis=1)
        maxi = tf.log(tf.nn.sigmoid(pos_scores - neg_scores))
        loss = tf.negative(tf.reduce_sum(maxi))
        return loss

    def regularization(self, users, pos_items, neg_items, filters_1, filters_2):
        regularizer = tf.nn.l2_loss(users) + tf.nn.l2_loss(pos_items) + tf.nn.l2_loss(neg_items)
        for k in range(self.layer):
            regularizer += tf.nn.l2_loss(filters_1[k]) + tf.nn.l2_loss(filters_2[k])
        return regularizer

    def adjacient_matrix(self, self_connection=False):
        A = np.zeros([self.n_users+self.n_items, self.n_users+self.n_items], dtype=np.float32)
        for (user, item) in self.graph:
            A[user, item + self.n_users] = 1
            A[item + self.n_users, user] = 1
        if self_connection == True:
            A += np.identity(self.n_users + self.n_items)
        return A.astype(np.float32)

    def degree_matrix(self):
        degree = np.sum(self.A, axis=1, keepdims=False)
        for i in range(len(degree)):
            degree[i] = max(degree[i], 0.1 ** 10)
        return degree

    def random_walk(self):
        temp = np.dot(np.diag(np.power(self.D, -0.5)), self.A)
        temp = np.dot(temp, np.diag(np.power(self.D, -0.5)))
        return temp.astype(np.float32)
    
    def dense_to_sparse(self, dense):
        idx = np.where(dense != 0)
        val = tf.constant(dense[idx], dtype=np.float32)
        idx = tf.constant(list(map(list, zip(*idx))), dtype=np.int64)
        shp = tf.constant([dense.shape[0],dense.shape[1]], dtype=np.int64)
        sparse = tf.SparseTensor(indices=idx, values=val, dense_shape=shp)
        return sparse
