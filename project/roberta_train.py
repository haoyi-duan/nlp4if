import numpy as np
import pandas as pd
import random
import copy
import argparse
from distutils.util import strtobool
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import transformers
from transformers import AutoModel, BertTokenizerFast, BertTokenizer
# Model Imports #
from models.roberta_basic import *
from models.roberta_CNN import *
from models.RobertAttentionClasswise import *
# Utils Imports #
from utils.preprocess import *
from utils.train_utils import *
import os
import wandb

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
torch.cuda.manual_seed_all(RANDOM_SEED)

#### Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-dtp", "--data_train_path", type=str, default="data/english/v3/v3_augmented/",
                    help="Expects a path to training folder")
parser.add_argument("-ddp", "--data_dev_path", type=str, default="data/english/v3/v3/",
                    help="Expects a path to dev folder")
parser.add_argument("-model", "--model_to_use", type=str, default="bert_train_emb",
                    help="Which model to use")
parser.add_argument("-bbase", "--base", type=str, default="roberta-large",
                    help="Which bert base model to use")
parser.add_argument("-msl", "--max_seq_len", type=int, default=56,
                    help="Maximum sequence length")
parser.add_argument("-bs", "--batch_size", type=int, default=32,
                    help="Batch Size")
parser.add_argument("-e", "--epochs", type=int, required=True,
                    help="Epochs")
parser.add_argument("-lr", "--learning_rate", type=float, default=1e-5,
                    help="Learning Rate of non-embedding params")
parser.add_argument("-dprob", "--dropout_prob", type=float, default=0.1,
                    help="Dropout Probability")
parser.add_argument("-lr_emb", "--learning_rate_embeddings", type=float, default=2e-5,
                    help="Learning Rate of embedding params")
parser.add_argument("-device", "--device", type=str, default="cuda",
                    help="Device")
parser.add_argument("-loss", "--loss_type", type=str, default="classwise_sum",
                    help="Loss")
parser.add_argument("-wdbr", "--wandb_run", type=str, required=True,
                    help="Wandb Run Name")
parser.add_argument("-log_to_wnb", "--log_to_wnb", type=strtobool, default=True,
                    help="Wandb Run Name")
parser.add_argument("-save_emb", "--save_emb", type=strtobool, default=False,
                    help="Save Model Embeddings")
parser.add_argument("-save_model", "--save_model", type=strtobool, default=False,
                    help="Save Model")

args = parser.parse_args()

# Add initial values here #
if args.log_to_wnb==True:
    wandb.init(name=args.wandb_run, project='bert', entity='haofeng')
    wandb.config.update(args)
###########################

### Base Parameters ###
device = torch.device(args.device)
print(device)
TRAIN_FILE=args.data_train_path#+"covid19_disinfo_binary_english_train.tsv"
DEV_FILE=args.data_dev_path#+"covid19_disinfo_binary_english_dev_input.tsv"
#######################

### Data Preparation ###
sentences, labels, train_les = process_data(TRAIN_FILE)
sentences_dev, labels_dev, train_les_dev = process_data(DEV_FILE)

train_x = sentences
train_y = labels
val_x = sentences_dev
val_y = labels_dev

# Generate class weights #
generate_class_weights(TRAIN_FILE)
########################

### Tokenize Data ###
tokens_train = roberta_tokenize(train_x, args.max_seq_len, base=args.base)
tokens_val = roberta_tokenize(val_x, args.max_seq_len, base=args.base)
tokens_dev = roberta_tokenize(sentences_dev, args.max_seq_len, base=args.base)

# tokens_train = tokenize(train_x, max_len=args.max_seq_len, bert_base=args.bert_base)
# tokens_val = tokenize(val_x, max_len=args.max_seq_len, bert_base=args.bert_base)
# tokens_dev = tokenize(sentences_dev, max_len=args.max_seq_len, bert_base=args.bert_base)

#####################

### Dataloader Preparation ###
# convert lists to tensors
train_seq = torch.tensor(tokens_train['input_ids'])
train_mask = torch.tensor(tokens_train['attention_mask'])
train_y = torch.tensor(train_y.tolist())

val_seq = torch.tensor(tokens_val['input_ids'])
val_mask = torch.tensor(tokens_val['attention_mask'])
val_y = torch.tensor(val_y.tolist())

dev_seq = torch.tensor(tokens_dev['input_ids'])
dev_mask = torch.tensor(tokens_dev['attention_mask'])
dev_y = torch.tensor(labels_dev.tolist())

# wrap tensors
train_data = TensorDataset(train_seq, train_mask, train_y)
# sampler for sampling the data during training
train_sampler = RandomSampler(train_data)
# dataLoader for train set
train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=args.batch_size)

# wrap tensors
val_data = TensorDataset(val_seq, val_mask, val_y)
# sampler for sampling the data during training
val_sampler = SequentialSampler(val_data)
# dataLoader for validation set
val_dataloader = DataLoader(val_data, sampler = val_sampler, batch_size=args.batch_size)

# dev tensors
dev_data = TensorDataset(dev_seq, dev_mask, dev_y)
# sampler for sampling the data during training
dev_sampler = SequentialSampler(dev_data)
# dataLoader for validation set
dev_dataloader = DataLoader(dev_data, sampler = dev_sampler, batch_size=args.batch_size)

################################

### Model Preparation ###
if args.model_to_use=="roberta_attn":
    model = ROBERTaAttention(freeze_bert_params=False, dropout_prob=args.dropout_prob, base=args.base)
elif args.model_to_use=="roberta_CNN":
    model = RobertaCNN(freeze_bert_params=False, dropout_prob=args.dropout_prob, base=args.base)
elif args.model_to_use=="roberta_attn_classwise":
    model = ROBERTaAttentionClasswise(freeze_bert_params=False, dropout_prob=args.dropout_prob, base=args.base)
model = model.to(device)

if args.log_to_wnb==True: 
    wandb.watch(model, log="all")
    
model = model.to(device)
#########################

### Train ###
if args.model_to_use=="robert_not_train_emb":
    model = train(model, train_dataloader, val_dataloader, args.device, args.epochs, 
                lr=args.learning_rate, loss_type=args.loss_type)
elif args.model_to_use=="roberta_train_emb":
    model = train_v2(model, train_dataloader, val_dataloader, args.device, args.epochs, 
                lr1=args.learning_rate, lr2=args.learning_rate_embeddings, loss_type=args.loss_type)
elif args.model_to_use=="roberta_attn":
    model = train_v2(model, train_dataloader, val_dataloader, args.device, args.epochs, 
                lr1=args.learning_rate, lr2=args.learning_rate_embeddings, loss_type=args.loss_type)
else: # default behavior
    model = train_v2(model, train_dataloader, val_dataloader, args.device, args.epochs, 
                lr1=args.learning_rate, lr2=args.learning_rate_embeddings, loss_type=args.loss_type)

### Print Stats ###
print("---Final Dev Stats---")
scores = evaluate_model(model, val_dataloader, args.device)
display_metrics(scores)

# Save summary wandb
if args.log_to_wnb==True:
    wandb.run.summary['Validation Mean F1-Score'] = np.mean(scores['f1'])
    wandb.run.summary['Validation Accuracy'] = np.mean(scores['acc'])
    wandb.run.summary['Validation Mean Precision'] = np.mean(scores['p_score'])
    wandb.run.summary['Validation Mean Recall'] = np.mean(scores['r_score'])
    wandb.run.summary['Validation Q1 F1 Score'] = scores['f1'][0]
    wandb.run.summary['Validation Q2 F1 Score'] = scores['f1'][1]
    wandb.run.summary['Validation Q3 F1 Score'] = scores['f1'][2]
    wandb.run.summary['Validation Q4 F1 Score'] = scores['f1'][3]
    wandb.run.summary['Validation Q5 F1 Score'] = scores['f1'][4]
    wandb.run.summary['Validation Q6 F1 Score'] = scores['f1'][5]
    wandb.run.summary['Validation Q7 F1 Score'] = scores['f1'][6]
    wandb.run.summary['Validation Q1 F1 Precision'] = scores['p_score'][0]
    wandb.run.summary['Validation Q2 F1 Precision'] = scores['p_score'][1]
    wandb.run.summary['Validation Q3 F1 Precision'] = scores['p_score'][2]
    wandb.run.summary['Validation Q4 F1 Precision'] = scores['p_score'][3]
    wandb.run.summary['Validation Q5 F1 Precision'] = scores['p_score'][4]
    wandb.run.summary['Validation Q6 F1 Precision'] = scores['p_score'][5]
    wandb.run.summary['Validation Q7 F1 Precision'] = scores['p_score'][6]

# Save model
if args.save_model:
    if not os.path.exists('bin'):
        os.mkdir('bin')

    torch.save(model.state_dict(), os.path.join('bin', args.wandb_run + '.pt'))
    torch.save(model.state_dict(), os.path.join(wandb.run.dir, args.wandb_run + '.pt'))

if args.save_emb==True:
    train_emb = get_model_embeddings(model, train_dataloader, args.device)
    val_emb = get_model_embeddings(model, val_dataloader, args.device)
    np.save(os.path.join(wandb.run.dir, "train_emb.npy"), train_emb)
    np.save(os.path.join(wandb.run.dir, "val_emb.npy"), val_emb)
