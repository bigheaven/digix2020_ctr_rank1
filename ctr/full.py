# -*- encoding: utf-8 -*-
'''
@File    :   full.py
@Time    :   2020/11/05 11:40:32
@Author  :   lyu
@Version :   1.0
@Contact :   lyu.scut@qq.com
@Desc    :   None
'''

# here put the import lib

import pandas as pd
import numpy as np
from tqdm import tqdm
from sklearn.model_selection import StratifiedKFold
from reduce.reduce import reduce, reduce_s
from gensim.models import Word2Vec
import logging
import lightgbm as lgb
from multiprocessing import Pool
import networkx as nx

def adjust(df, key, feature):
	if key == 'uid':
		mean7 = df[df['pt_d'] < 8][feature].mean()
		std7 = df[df['pt_d'] < 8][feature].std()
		mean8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)][feature].mean()
		std8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)][feature].std()
	        #利用样本均值和修正样本标准差来拟合概率分布特性，将第8天冷启动的特征分布归一化到前7天上去
		df.loc[(df['pt_d'] >= 8) & (df['coldu'] == 1), feature]= ((df[(df['pt_d'] >= 8) & (df['coldu'] == 1)][feature] - mean8) / std8 * std7 + mean7)
	return df

# def adjust(df, key, feature):
# 	if key == 'uid':
# 		mean7 = df[df['pt_d'] < 8][feature].mean()
# 		std7 = df[df['pt_d'] < 8][feature].std()
# 		mean8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)][feature].mean()
# 		std8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)][feature].std()
# 		df.loc[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0), feature]= ((df[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0)][feature] - mean8) / std8 * std7 + mean7)
# 	return df

# def adjust_single(df, key, feature):
# 	if key == 'uid':
# 		mean7 = df[df['pt_d'] < 8].drop_duplicates(['uid'])[feature].mean()
# 		std7 = df[df['pt_d'] < 8].drop_duplicates(['uid'])[feature].std()
# 		mean8 = df[(df['coldu'] == 1)].drop_duplicates(['uid'])[feature].mean()
# 		std8 = df[(df['coldu'] == 1)].drop_duplicates(['uid'])[feature].std()
# 		df.loc[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0), feature]= ((df[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0)][feature] - mean8) / std8 * std7 + mean7)
# 	return df

def adjust_single(df, key, feature): #在统计特征里，key是原始特征列名，feature是特征列名_count
	if key == 'uid':#         对前7天的uid去重
		mean7 = df[df['pt_d'] < 8].drop_duplicates(['uid'])[feature].mean() #求平均
		std7 = df[df['pt_d'] < 8].drop_duplicates(['uid'])[feature].std() #求标准差
	        #                      第8天，冷启动用户
		mean8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)].drop_duplicates(['uid'])[feature].mean()
		std8 = df[(df['pt_d'] >= 8) & (df['coldu'] == 1)].drop_duplicates(['uid'])[feature].std()
	        # 利用样本均值和修正样本标准差来拟合概率分布特性，将第8天冷启动的特征分布归一化到前7天上去
		df.loc[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0), feature]= ((df[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 0)][feature] - mean8) / std8 * std7 + mean7 * 1.1)
		df.loc[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 1), feature]= ((df[(df['pt_d'] == 10) & (df['coldu'] == 1) & (df['coldt'] == 1)][feature] - mean8) / std8 * std7 * 0.8 + mean7 * 0.8)
	return df

def group_fea(df,key,target): #对用户来说，key是uid，target是各个广告相关特征
	tmp = df.groupby(key, as_index=False)[target].agg({
		key + '_' + target + '_nunique': 'nunique', #统计唯一值个数。这里把target列名也改成了后一种
	}).reset_index().drop('index', axis=1)
	return tmp

def emb(df, f1, f2):
	emb_size = 8
	tmp = df.groupby(f1, as_index=False)[f2].agg({'{}_{}_list'.format(f1, f2): list})
	sentences = tmp['{}_{}_list'.format(f1, f2)].values.tolist()
	del tmp['{}_{}_list'.format(f1, f2)]
	for i in range(len(sentences)):
		sentences[i] = [str(x) for x in sentences[i]]
	model = Word2Vec(sentences, size=emb_size, window=6, min_count=5, sg=0, hs=0, seed=1, iter=5)
	emb_matrix = []
	for seq in sentences:
		vec = []
		for w in seq:
			if w in model.wv.vocab:
				vec.append(model.wv[w])
		if len(vec) > 0:
			emb_matrix.append(np.mean(vec, axis=0))
		else:
			emb_matrix.append([0] * emb_size)
	emb_matrix = np.array(emb_matrix)
	for i in range(emb_size):
		tmp['{}_{}_emb_{}'.format(f1, f2, i)] = emb_matrix[:, i]
	return tmp

def emb2(df, f1, f2):
	emb_size = 8
	tmp = df.groupby(f1, as_index=False)[f2].agg({'{}_{}_list'.format(f1, f2): list})
	sentences = tmp['{}_{}_list'.format(f1, f2)].values.tolist()
	del tmp['{}_{}_list'.format(f1, f2)]
	for i in range(len(sentences)):
		sentences[i] = [str(x) for x in sentences[i]]
	model = Word2Vec(sentences, size=emb_size, window=6, min_count=5, sg=0, hs=0, seed=1, iter=5)
	emb_matrix = []
	for seq in sentences:
		vec = []
		for w in seq:
			if w in model.wv.vocab:
				vec.append(model.wv[w])
		if len(vec) > 0:
			emb_matrix.append(np.mean(vec, axis=0))
		else:
			emb_matrix.append([0] * emb_size)
	emb_matrix = np.array(emb_matrix)
	for i in range(emb_size):
		tmp['{}_{}_emb_{}'.format(f1, f2, i)] = emb_matrix[:, i]
	
	word_list = []
	emb_matrix2 = []
	for w in model.wv.vocab:
		word_list.append(w)
		emb_matrix2.append(model.wv[w])
	emb_matrix2 = np.array(emb_matrix2)
	tmp2 = pd.DataFrame()
	tmp2[f2] = np.array(word_list).astype('int')
	for i in range(emb_size):
		tmp2['{}_{}_emb_{}'.format(f2, f1, i)] = emb_matrix2[:, i]
	return tmp, tmp2

def emb_adjust(df, f1, f2): #df已经根据pt_d排序，f1是uid f2是adv_id
	emb_size = 8
	df = df.fillna(0)
	tmp = df.groupby(f1, as_index=False)[f2].agg({'{}_{}_list'.format(f1, f2): list}) #竟然还可以是list？
#格式类似如下：
# 	userid                                     user_feed_list
#0           8  [71474, 73916, 50282, 11391, 27349, 30287, 115...
	sentences = tmp['{}_{}_list'.format(f1, f2)].values.tolist() #[[1,87,...][][][]] 还是数字，不是str
	for i in range(len(sentences)):
		sentences[i] = [str(x) for x in sentences[i]] #变成类似于list里面有对应每个样本的词[['1','87',...][][][]]
	model = Word2Vec(sentences, size=emb_size, window=6, min_count=5, sg=0, hs=0, seed=1, iter=5)

	index_dict = {}
	emb_matrix = []
	for i in tqdm(range(len(sentences))):
		seq = sentences[i]
		vec = []
		for w in seq:
			if w in model.wv.vocab: #这个应该一定存在把？不一定，出现次数少于5就没有
				vec.append(model.wv[w]) #表示这个词的特征映射结果
		if len(vec) > 0:
			emb_matrix.append(np.mean(vec, axis=0)) #求每列均值。[[1, 2], [3, 4]] -> [ 2.,  3.]。每行8各元素，最后得到每列的均值
		else:
			emb_matrix.append([0] * emb_size) #没有特征映射则为0
		index_dict[tmp[f1][i]] = i  #f1是uid，i表示第i行 tmp[f1][i]表示的是第i行的uid
	emb_matrix = np.array(emb_matrix) #转格式
	for i in range(emb_size): #8
		tmp['{}_of_{}_emb_{}'.format(f1, f2, i)] = emb_matrix[:, i] #第0维取全部，第1维取第i个元素。每个advid作为词向量，用向量平均来代表每个uid。

	tmp_f2 = df.groupby(f2, as_index=False)[f1].agg({'{}_{}_list'.format(f2, f1): list}) #只是为下面adjust服务的。
	sentences_f2 = tmp_f2['{}_{}_list'.format(f2, f1)].values.tolist() #这里没有做w2v ？
	index_dict_f2 = {}
	emb_matrix_f2 = []
	for i in tqdm(range(len(sentences_f2))):
		seq = sentences_f2[i] #存的是每个advid对应的uid
		vec = []
		for w in seq:
			vec.append(emb_matrix[index_dict[w]]) #index_dict[w]是uid的行号，emb_matrix[index_dict[w]]得到这个uid的8位向量
		if len(vec) > 0:
			emb_matrix_f2.append(np.mean(vec, axis=0))
		else:
			emb_matrix_f2.append([0] * emb_size)
		index_dict_f2[str(tmp_f2[f2][i])] = i #f2是advid，i表示第行 tmp[f2][i]表示的是第i行的adv_id
	emb_matrix_f2 = np.array(emb_matrix_f2) #这一步是用uid的向量来反求advid的向量。（w2v真正只对advid有词向量）

	emb_matrix_adjust = [] #这个和上一步有啥区别 ？
	for seq in tqdm(sentences): #针对f1-f2-list.seq里面放的是某个f1下面所有f2组成的list
		vec = []
		for w in seq:
			vec.append(emb_matrix_f2[index_dict_f2[w]]) #index_dict_f2[w]得到每个adv_id的在tmp_f2的行号.emb_matrix_f2是这个advid的8位emb
		if len(vec) > 0:
			emb_matrix_adjust.append(np.mean(vec, axis=0)) #有平均了一次。总的过程是advid向量-平均> uid向量-平均>advid向量- 平均adjust>uid向量
		else:
			emb_matrix_adjust.append([0] * emb_size)
	emb_matrix_adjust = np.array(emb_matrix_adjust)
	for i in range(emb_size):
		tmp['{}_of_{}_emb_adjust_{}'.format(f1, f2, i)] = emb_matrix_adjust[:, i] #与154行没有adjust的区别

	tmp = tmp.drop('{}_{}_list'.format(f1, f2), axis=1)
	
	word_list = []
	emb_matrix2 = []
	for w in tqdm(model.wv.vocab): #这里的词典是所有advid
		word_list.append(w)
		emb_matrix2.append(model.wv[w])
	emb_matrix2 = np.array(emb_matrix2)
	tmp2 = pd.DataFrame()
	tmp2[f2] = np.array(word_list).astype('int') #所有advid
	for i in range(emb_size): #8
		tmp2['{}_emb_{}'.format(f2, i)] = emb_matrix2[:, i]#f2几乎所有词的emb。分成8列返回
	
	return tmp, tmp2

def randomWalk(_g, _corpus_num, _deep_num, _current_word):
	_corpus = []
	for _ in range(_corpus_num):
		sentence = [_current_word]
		current_word = _current_word
		count = 0
		while count<_deep_num:
			count+=1
			_node_list = list(_g[current_word].keys())
			_weight_list = np.array([item['weight'] for item in (_g[current_word].values())])
			_ps = _weight_list / np.sum(_weight_list)
			sel_node = roulette(_node_list, _ps)
			if count % 2 == 0:
				sentence.append(sel_node)
			current_word = sel_node
		_corpus.append(sentence)
	return _corpus

def roulette(_datas, _ps):
	return np.random.choice(_datas, p=_ps)

def build_graph(df, f1, f2):
	G = nx.Graph()
	df_weight = df.groupby([f1, f2], as_index=False)['gender'].agg({'weight': 'count',}).reset_index().drop('index', axis=1)
	df_weight[f1 + '_word'] = df_weight[f1].astype(str) + '_' + f1
	df_weight[f2 + '_word'] = df_weight[f2].astype(str) + '_' + f2
	df_weight = df_weight.drop(f1, axis=1).drop(f2, axis=1)
	for i in tqdm(range(len(df_weight))):
		G.add_edge(df_weight[f1 + '_word'][i], df_weight[f2 + '_word'][i], weight=df_weight['weight'][i])
	return G, df_weight

def deep_walk(G, df_weight, f1, f2):
	num = 5
	deep_num = 20
	f2_set = set(df_weight[f2 + '_word'])
	sentences = []
	for word in tqdm(f2_set):
		corpus = randomWalk(G, num, deep_num, word)
		sentences += corpus
	return sentences

def deep_walk_pool(G, f2_set, f1, f2):
	num = 5
	deep_num = 40
	sentences = []
	for word in tqdm(f2_set):
		corpus = randomWalk(G, num, deep_num, word)
		sentences += corpus
	return sentences

def graph_emb(sentences, G, df_weight, f1, f2):
	emb_size = 8
	model = Word2Vec(sentences, size=emb_size, window=6, min_count=5, sg=0, hs=0, seed=1, iter=5)
	f1_set = list(set(df_weight[f1 + '_word']))
	emb_matrix = []
	tmp = pd.DataFrame()
	tmp[f1 + '_word'] = f1_set
	for f1_word in f1_set:
		vec = []
		for f2_word in G[f1_word].keys():
			if f2_word in model.wv.vocab:
				vec.append(model.wv[f2_word])
		if len(vec) > 0:
			emb_matrix.append(np.mean(vec, axis=0))
		else:
			emb_matrix.append([0] * emb_size)
	emb_matrix = np.array(emb_matrix)
	for i in range(emb_size):
		tmp['{}_{}_graph_emb_{}'.format(f1, f2, i)] = emb_matrix[:, i]
	
	word_list = []
	emb_matrix2 = []
	for w in model.wv.vocab:
		word_list.append(w)
		emb_matrix2.append(model.wv[w])
	emb_matrix2 = np.array(emb_matrix2)
	tmp2 = pd.DataFrame()
	tmp2[f2 + '_word'] = word_list
	for i in range(8):
		tmp2['{}_{}_graph_emb_{}'.format(f2, f1, i)] = emb_matrix2[:, i]
	return tmp, tmp2

def make_feature(df):

	# count特征
	print('开始构造count特征')
	cate_cols = ['uid', 'task_id', 'adv_id', 'creat_type_cd', 'adv_prim_id', 'dev_id', 'inter_type_cd', 'slot_id',
					'spread_app_id', 'tags', 'app_first_class', 'app_second_class', 'city', 'city_rank', 'device_name',
					'device_size', 'career', 'gender', 'net_type', 'residence', 'app_score', 'emui_dev','consume_purchase', 'indu_name']
	for f in tqdm(cate_cols):
		tmp = df[f].map(df[f].value_counts()) #直接替换成各自值的统计个数
		if tmp.var() > 1: #方差 实际值-平均值 ^ 2 再除以值个数
			df[f + '_count'] = tmp
			df = adjust_single(df, f, f + '_count') #只处理uid #修正冷启动特征分布

#     # nunique特征
	print('开始构造nunique特征') #唯一值特征 ？
	nunique_group = []

	print('用户')
	key = 'uid'
	feature_target = ['task_id', 'adv_id', 'dev_id', 'indu_name', 'adv_prim_id',  'slot_id', 'spread_app_id']
	for target in tqdm(feature_target):
		if key + '_' + target + '_nunique' not in nunique_group:
			nunique_group.append(key + '_' + target + '_nunique')
			tmp = group_fea(df,key,target) #每个uid 对应其他特征，统计唯一值的个数
			df = df.merge(tmp,on=key,how='left')
			df = adjust_single(df, key, key + '_' + target + '_nunique') #修正冷启动user的特征分布
		if target + '_' + key + '_nunique' not in nunique_group:
			nunique_group.append(target + '_' + key + '_nunique')
			tmp = group_fea(df,target,key) #这个牛啊 双向特征
			df = df.merge(tmp,on=target,how='left')

	print('广告')
	key = 'adv_id' #广告语用户侧+媒体测特征 统计。没有冷启动问题
	feature_target = ['uid', 'age', 'city', 'device_name', 'device_size', 'career', 'residence', 'gender', 'adv_prim_id', 'slot_id', 'spread_app_id']
	for target in tqdm(feature_target):
		if key + '_' + target + '_nunique' not in nunique_group:
			nunique_group.append(key + '_' + target + '_nunique')
			tmp = group_fea(df,key,target)
			df = df.merge(tmp,on=key,how='left')
		if target + '_' + key + '_nunique' not in nunique_group:
			nunique_group.append(target + '_' + key + '_nunique')
			tmp = group_fea(df,target,key)
			df = df.merge(tmp,on=target,how='left')

	print('清除')
	for feature in tqdm(nunique_group):
		if df[feature].var()<1: #方差小于1列清楚
			df = df.drop(feature, axis=1)

	df = reduce(df) #压缩

	# embedding特征
	print('开始构造emb特征')
	emb_cols = [['uid', 'adv_id']]
	sort_df = df.sort_values('pt_d').reset_index(drop=True) #升序排列
	for f1, f2 in emb_cols: # f1:uid f2:adv_id
		tmp, tmp2 = emb_adjust(sort_df, f1, f2) #返回的是用advid给uid表示的向量，tmp2是每个advid的向量
		df = df.merge(tmp, on=f1, how='left').merge(tmp2, on=f2, how='left').fillna(0) #把每个uid和advid的向量都拼在每条数据后面

	# ctr特征
	print('开始构造ctr特征')
	mean_rate = df[df['pt_d'] < 8]['label'].mean() #前7天label均值。所有值的平均值
	feature_list = cate_cols
	for feat_1 in tqdm(feature_list):
		res = pd.DataFrame()
		for period in [1, 2, 3, 4, 5, 6, 7, 10]:
			if period == 1:
				count = df[df['pt_d'] <= period].groupby(feat_1, as_index=False)['label'].agg({feat_1 + '_rate': 'mean'})
			elif period == 10:
				count = df[df['pt_d'] < 8].groupby(feat_1, as_index=False)['label'].agg({feat_1 + '_rate': 'mean'})
			else:
				count = df[df['pt_d'] < period].groupby(feat_1, as_index=False)['label'].agg({feat_1 + '_rate': 'mean'})
			count['pt_d'] = period
			res = res.append(count, ignore_index=True)#同一个特征，不同天数，上下拼接
		df = pd.merge(df, res, how='left', on=[feat_1, 'pt_d'], sort=False) #feat_1 + '_rate' 拼到后面去了。
		df[feat_1 + '_rate'] = reduce_s(df[feat_1 + '_rate'].fillna(mean_rate)) #压缩并且把NaN的值变成均值
		print(feat_1, ' over')

		
	# df_trans = df[df['pt_d']==7].copy().sample(frac=0.3, random_state=1)
	# df_trans['uid_rate'] = mean_rate
	# df = pd.concat([df,df_trans], axis=0).reset_index(drop=True)

	df = df.reset_index() #加一个index列
	df_trans = df[df['pt_d']==7][['index']].sample(frac=0.3, random_state=1) #抽取0.3比例的index出来
	df_trans['trans'] = 1 #加trans列
	df = df.merge(df_trans,on='index',how='left') #把上面抽到的index对应的行，拼接一个trans列并且值为1
	df.loc[df['trans'] == 1, 'uid_rate'] = df[df['pt_d'] < 7]['label'].mean() #把trans=1的行取出来，对应的rate设置为前7天的平均值
	df = df.drop('index', axis=1).drop('trans', axis=1) #删掉这两列

	df = reduce(df)

	return df

#i 0~3 xx_idx df0里train和val的下标 df0：train里面label全为0的样本 df1：全为1的样本 test_df_raw：是testAB全合并
def atom_makefea(i,trn_idx, val_idx, df0, df1,test_df_raw, fold):
	print('fold:{}'.format(i + 1))
	#                 通过行号取行数据                        上下合并
	df = pd.concat([df0.iloc[val_idx].reset_index(drop=True),df1], axis=0).reset_index(drop=True)

	df = pd.concat([df,test_df_raw], axis=0).reset_index(drop=True)
                         #包含了df0 df1 和testAB的数据
	df = make_feature(df)

	df.to_pickle('./data/feature/fea_'+str(fold)+'_'+str(i+1)+'.pkl')
	print('save fea to fea.pkl!', i+1)
	return 

def atom_prediction(i, fold, epoch=550):
	params = {
		'boosting_type': 'gbdt',
		'objective': 'binary',
		'metric': 'auc',
		'boost_from_average' : True,
		'train_metric': True, 
		'feature_fraction_seed' : 1,
		'learning_rate': 0.05,
		'is_unbalance': False,  #当训练数据是不平衡的，正负样本相差悬殊的时候，可以将这个属性设为true,此时会自动给少的样本赋予更高的权重
		'num_leaves': 256,  # 一般设为少于2^(max_depth)
		'max_depth': -1,  #最大的树深，设为-1时表示不限制树的深度
		'min_child_samples': 15,  # 每个叶子结点最少包含的样本数量，用于正则化，避免过拟合
		'max_bin': 200,  # 设置连续特征或大量类型的离散特征的bins的数量
		'subsample': 1,  # Subsample ratio of the training instance.
		'subsample_freq': 1,  # frequence of subsample, <=0 means no enable
		'colsample_bytree': 0.5,  # Subsample ratio of columns when constructing each tree.
		'min_child_weight': 0,  # Minimum sum of instance weight(hessian) needed in a child(leaf)
		'subsample_for_bin': 200000,  # Number of samples for constructing bin
		'min_split_gain': 0,  # lambda_l1, lambda_l2 and min_gain_to_split to regularization
		'reg_alpha': 2.99,  # L1 regularization term on weights
		'reg_lambda': 1.9,  # L2 regularization term on weights
		'nthread': 20,
		'verbose': 0,
		}
	
	print('predict fold:{}'.format(i + 1))
	df = pd.read_pickle('./data/feature/fea_'+str(fold)+'_'+str(i+1)+'.pkl')
	
	test_df = df[df["pt_d"]==10].reset_index(drop=True)
	train_df = df[df["pt_d"]<8].reset_index(drop=True)

	X_train = train_df
	y_train = X_train["label"].astype('int32')
	drop_fea = ['index', 'id', 'pt_d', 'coldu', 'label', 'communication_onlinerate', 'testb', 'coldt']
	feature = [x for x in X_train.columns if x not in drop_fea]
	print(feature)
	weight = X_train['pt_d'] / X_train['pt_d'].max() #越靠近日期权重越大
	lgb_train = lgb.Dataset(X_train[feature], y_train, weight = weight)

	gbm = lgb.train(params, lgb_train, num_boost_round=epoch,  valid_sets=(lgb_train), verbose_eval = 50)
	# gbm = lgb.train(params, lgb_train, num_boost_round=epoch)

	preds = gbm.predict(test_df[feature], num_iteration=gbm.best_iteration) / fold

	res = pd.DataFrame()
	res['id'] = test_df['id'].astype('int32')
	res['probability'] = preds
	res['probability'] = res['probability'].astype(np.float32)
	res.to_csv('result/submission_'+str(fold)+'_'+str(i+1)+'.csv',index = False)

	print('save fold:{}'.format(i + 1))
	return

from joblib import Parallel, delayed #分布式计算模块
if __name__ == "__main__":

#     logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s', level=logging.INFO)

	df_raw = pd.read_pickle('./data/train_data.pkl')

	df0 = df_raw[df_raw['label']==0].copy()
	df1 = df_raw[df_raw['label']==1].copy()

	test_df_A  = pd.read_pickle('./data/test_data_A.pkl')
	test_df_B = pd.read_pickle('./data/test_data_B.pkl')
	# test_df_A['pt_d'] = 10
	# test_df_A['testb'] = 0
	# test_df_B['testb'] = 1
	train_uid = set(df_raw['uid'])
	test_df_A['coldu'] = test_df_A['uid'].apply(lambda x: 1 if x not in train_uid else 0) #冷启动用户
	test_df_B['coldu'] = test_df_B['uid'].apply(lambda x: 1 if x not in train_uid else 0)
	train_uid = set(list(set(df_raw['uid'])) + list(set(test_df_A['uid']))) #train里的uid和A的uid取交集
	test_df_B['coldt'] = test_df_B['uid'].apply(lambda x: 1 if x not in train_uid else 0) #冷启动用户，拿第二遍
	test_df_raw = pd.concat([test_df_A,test_df_B], axis=0).reset_index(drop=True) #上下合并
	# train_uid = set(df_raw['uid'])
	# test_df_raw['coldu'] = test_df_raw['uid'].apply(lambda x: 1 if x not in train_uid else 0)
	del df_raw

	epoch = 550
	fold = 4
	preds = 0
	print('开始{}折制作特征'.format(fold)) 
	skf = StratifiedKFold(n_splits=fold, shuffle=True, random_state=1) #验证集不同类别比例相同，所以要传入类别。返回的4组数据分别是train和test的index        pt_d行为发生时间(0~8)
	Parallel(n_jobs=fold)(delayed(atom_makefea)(i,trn_idx, val_idx, df0, df1,test_df_raw, fold) for i, (trn_idx, val_idx) in enumerate(skf.split(df0, df0['pt_d'])))
        #n_jobs表示CPU核数。delayed就是个装饰器，接受一个函数及其参数，包装成一个对象。
	print('开始{}折训练'.format(fold))
	# Parallel(n_jobs=2)(delayed(atom_prediction)(i, fold, epoch) for i in range(fold))
	for i in range(fold):
		atom_prediction(i, fold, epoch)
	
	print('开始{}折结果融合'.format(fold))
	preds = np.zeros(2000000)
	res = pd.read_csv('result/submission_'+str(fold)+'_'+str(1)+'.csv')
	for i in range(fold):
		res_ = pd.read_csv('result/submission_'+str(fold)+'_'+str(i+1)+'.csv')
		preds+=res_['probability']
	res['probability'] = preds
	res['probability'] = res['probability'].astype(np.float32)
	res.to_csv('result/submission_'+str(fold)+'_all.csv',index = False)
