#-*-coding:utf-8-*-
import torch
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torch.nn import functional as F
import utils.dataset as dataset
import torchvision
import torchvision.datasets.folder as folder
import math
import os
import getpass
import shutil
import argparse


parser = argparse.ArgumentParser(description='Pytorch Distillation Experiment')
parser.add_argument('--arch', metavar='ARCH', default='alexnet', help='model architecture')
parser.add_argument('--data_name', metavar='DATA_NAME', type=str, default='Flower102', help='dataset name')
parser.add_argument('--zero_train', default=False, type=bool, help='choose if train from Scratch or not')

args = parser.parse_args()

import logging
#======================generate logging imformation===============
log_path = './log'
if not os.path.exists(log_path):
    os.mkdir(log_path)

# you should assign log_name first such as mobilenet_resnet50_CIFAR10.log
log_name = 'hhhh.log'
TrainInfoPath = os.path.join(log_path, log_name)
# formater
formatter = logging.Formatter('%(levelname)s %(message)s')
# cmd Handler 
cmdHandler = logging.StreamHandler() 
# File Handler including info
infoFileHandler = logging.FileHandler(TrainInfoPath, mode='w')
infoFileHandler.setFormatter(formatter)
# info Logger
infoLogger = logging.getLogger('info') 
infoLogger.setLevel(logging.DEBUG) 
infoLogger.addHandler(cmdHandler)
infoLogger.addHandler(infoFileHandler)

if getpass.getuser() == 'tsq':
    train_batch_size = 8
else:
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    train_batch_size = 32

use_gpu = torch.cuda.is_available()
num_batches = 0


def val_test(model, val_loader, test_loader):
    model.eval()
    val_correct = 0
    val_total = 0
    test_correct = 0
    test_total = 0

    for i, (batch, label) in enumerate(val_loader):
        batch = batch.cuda()
        output = model(Variable(batch))
        pred_label = output.data.max(1)[1] # 返回模型预测概率最大的标签
        val_correct += pred_label.cpu().eq(label).sum() # label为torch.LongTensor类型
        val_total += label.size(0)

    for i, (batch, label) in enumerate(test_loader):
        batch = batch.cuda()
        output = model(Variable(batch))
        pred_label = output.data.max(1)[1] # 返回模型预测概率最大的标签
        test_correct += pred_label.cpu().eq(label).sum() # label为torch.LongTensor类型
        test_total += label.size(0)

    infoLogger.info("Val  Accuracy :"+str(round( float(val_correct) / val_total , 3 )))
    infoLogger.info("Test Accuracy :"+str(round( float(test_correct) / test_total , 3 )))
    model.train()
    return round( float(test_correct) / test_total , 3 )

def test(model, test_loader):
    model.eval()
    test_correct = 0
    test_total = 0

    for i, (batch, label) in enumerate(test_loader):
        batch = batch.cuda()
        output = model(Variable(batch))
        pred_label = output.data.max(1)[1] # 返回模型预测概率最大的标签
        test_correct += pred_label.cpu().eq(label).sum() # label为torch.LongTensor类型
        test_total += label.size(0)

    infoLogger.info("Test Accuracy :"+str(round( float(test_correct) / test_total , 3 )))
    model.train()
    return round( float(test_correct) / test_total , 3 )

def train_batch(model, optimizer, batch, label): 
    optimizer.zero_grad() # 
    input = Variable(batch)
    output = model(input)
    criterion = torch.nn.CrossEntropyLoss()
    criterion(output, Variable(label)).backward() 
    optimizer.step()
    return criterion(output, Variable(label)).data

def train_epoch(model, train_loader, optimizer=None):
    global num_batches
    for batch, label in train_loader:
        loss = train_batch(model, optimizer, batch.cuda(), label.cuda())
        if num_batches%1 == 0:
            infoLogger.info('%23s%-9s%-13s'%('the '+str(num_batches)+'th batch, ','loss is: ',str(round(loss[0],8))))
        num_batches +=1

# 训练一个epoch,测试一次
def train_test(model, train_loader, test_loader, optimizer=None, epoches=10):
    print("Start training.")
    if optimizer is None:
        optimizer = optim.SGD(model.parameters(), lr = 0.001, momentum=0.9)

    for i in range(epoches):
        model.train()
        print("Epoch: ", i)
        train_epoch(model, train_loader, optimizer)
        if i%10==0:
            acc = test(model, test_loader)
        filename = './models/' + args.arch + '_' + args.data_name + '_' + str(acc) + '.pth'
        torch.save(model.state_dict(), filename)
    print("Finished training.")

# 训练一个epoch,测试一次
def train_val_test(model, train_loader, val_loader, test_loader, optimizer=None, epoches=10):
    print("Start training.")
    if optimizer is None:
        optimizer = optim.SGD(model.parameters(), lr = 0.001, momentum=0.9)

    for i in range(epoches):
        model.train()
        infoLogger.info("Epoch: "+str(i))
        train_epoch(model, train_loader, optimizer)
        if i%10==0:
            acc = val_test(model, val_loader, test_loader)
            filename = './1x1models/' + '1x1' + args.arch + '_' + args.data_name + '_' + str(acc) + '.pth'
            state = model.state_dict()
            torch.save(state, filename)
        else:
            state = model.state_dict()
        s1x1ParaName = ['features1.3.weight','features2.3.weight','features3.2.weight','features4.2.weight','features5.3.weight']
        for name in s1x1ParaName:
            sumStr = name+'  sum  is: '+str(state[name].sum())
            meanStr = name+'  mean is: '+str(torch.mean(state[name]))
            stdStr = name+'  std  is: '+str(torch.std(state[name]))
            infoLogger.info(sumStr)
            infoLogger.info(meanStr)
            infoLogger.info(stdStr)

    infoLogger.info("Finished training.")

# add a 1x1 depthwise conv layer between former conv layers
class AddLayerAlexNet(nn.Module):
    def __init__(self, num_classes=2):
        super(AddLayerAlexNet, self).__init__()
        model = torchvision.models.alexnet(pretrained=False)
        layer_list11 = []
        layer_list12 = []
        layer_list21 = []
        layer_list22 = []
        layer_list31 = []
        layer_list32 = []
        layer_list41 = []
        layer_list42 = []
        layer_list51 = []
        layer_list52 = []
        for i, layer in enumerate(model.features):
            if i<=2:
                layer_list11.append(layer)
                if i==0:
                    channels = layer.out_channels
                if i==2:
                    layer_list12.append(nn.Conv2d(in_channels=channels,out_channels=channels,kernel_size=1,stride=1,groups=channels,bias=False))
            elif i<=5:
                layer_list21.append(layer)
                if i==3:
                    channels = layer.out_channels
                if i==5:
                    layer_list22.append(nn.Conv2d(in_channels=channels,out_channels=channels,kernel_size=1,stride=1,groups=channels,bias=False))
            elif i<=7:
                layer_list31.append(layer)
                if i==6:
                    channels = layer.out_channels
                if i==7:
                    layer_list32.append(nn.Conv2d(in_channels=channels,out_channels=channels,kernel_size=1,stride=1,groups=channels,bias=False))
            elif i<=9:
                layer_list41.append(layer)
                if i==8:
                    channels = layer.out_channels
                if i==9:
                    layer_list42.append(nn.Conv2d(in_channels=channels,out_channels=channels,kernel_size=1,stride=1,groups=channels,bias=False))
            elif i<=12:
                layer_list51.append(layer)
                if i==10:
                    channels = layer.out_channels
                if i==12:
                    layer_list52.append(nn.Conv2d(in_channels=channels,out_channels=channels,kernel_size=1,stride=1,groups=channels,bias=False))

        # add a 1x1 depthwise conv layer and a mask layer
        self.features11 = nn.Sequential(*layer_list11)
        self.features12 = nn.Sequential(*layer_list12)
        self.features21 = nn.Sequential(*layer_list21)
        self.features22 = nn.Sequential(*layer_list22)
        self.features31 = nn.Sequential(*layer_list31)
        self.features32 = nn.Sequential(*layer_list32)
        self.features41 = nn.Sequential(*layer_list41)
        self.features42 = nn.Sequential(*layer_list42)
        self.features51 = nn.Sequential(*layer_list51)
        self.features52 = nn.Sequential(*layer_list52)

        for param in self.features11.parameters():
            param.requires_grad = False
        for param in self.features12.parameters():
            param.requires_grad = True

        for param in self.features21.parameters():
            param.requires_grad = False
        for param in self.features22.parameters():
            param.requires_grad = True

        for param in self.features31.parameters():
            param.requires_grad = False
        for param in self.features32.parameters():
            param.requires_grad = True

        for param in self.features41.parameters():
            param.requires_grad = False
        for param in self.features42.parameters():
            param.requires_grad = True

        for param in self.features51.parameters():
            param.requires_grad = False
        for param in self.features52.parameters():
            param.requires_grad = True
       
        self.num_classes = num_classes
        self.classifier = nn.Sequential(
            nn.Dropout(),
            nn.Linear(256 * 6 * 6, 4096),
            nn.ReLU(inplace=True),
            nn.Dropout(),
            nn.Linear(4096, 4096),
            nn.ReLU(inplace=True),
            nn.Linear(4096, num_classes),
        )

    def forward(self, x):
        x = self.features11(x)
        x = self.features12(x)
        x = self.features21(x)
        x = self.features22(x)
        x = self.features31(x)
        x = self.features32(x)
        x = self.features41(x)
        x = self.features42(x)
        x = self.features51(x)
        x = self.features52(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x

# for alxenet, 1x1 layers indexs should be [2 5 8 11 14]
# all layers indexs is [0 1 2 .... 20] 21=16+5
# 1x1 model load paras from original model 
def my_load_state_dict(model, state_dict):
    own_state = model.state_dict()
    j = 0
    for i in range(21):
        if i in [2, 5, 8, 11, 14]:
            shape = own_state.items()[i][1].shape
            own_state.items()[i][1].copy_(torch.ones(shape)) # init with 1
        else:
            own_state.items()[i][1].copy_(state_dict.items()[j][1])
            j +=1


def main():
    # you should set data path on the top
    global train_path, val_path, test_path
    global train_batch_size
    if 'Flower102' in args.data_name:
        train_path = "./Flower102/train"
        test_path = "./Flower102/test"
        val_path = "./Flower102/val"
    elif 'Birds200' in args.data_name:
        train_path = "./Birds200/train"
        test_path = "./Birds200/test"
    # global train_path, test_path
    if 'Flower102' in train_path:
        model = AddLayerAlexNet(102)
        train_loader = dataset.train_loader(train_path, batch_size=train_batch_size, num_workers=4, pin_memory=True)
        val_loader = dataset.test_loader(val_path, batch_size=1, num_workers=4, pin_memory=True)
        test_loader = dataset.test_loader(test_path, batch_size=1, num_workers=4, pin_memory=True)
    elif 'Birds200' in train_path:
        model = AddLayerAlexNet(200)
        train_loader = dataset.train_loader(train_path, batch_size=train_batch_size, num_workers=4, pin_memory=True)
        test_loader = dataset.test_loader(test_path, batch_size=1, num_workers=4, pin_memory=True)
    if use_gpu:
        model = model.cuda()
        print("Use GPU!")
    else:
        print("Use CPU!")

    checkpoint = torch.load('./1x1models/origin1x1alexnet_Flower102_0.789.pth')
    model.load_state_dict(checkpoint, strict=True)

    if 'Flower102' in train_path:
        train_val_test(model, train_loader, val_loader, test_loader, optimizer=None, epoches=50)
    elif 'Birds200' in train_path:
        train_test(model, train_loader, test_loader, optimizer=None, epoches=10)




if __name__ == "__main__":
    main()


# usage
# python alexnetPrune.py --arch alexnet --data_name Flower102


############predict single img############
#     classes, class_to_idx = folder.find_classes('./Flower102/train/')
#     # load one jpg, convert to Variable
#     root = '/home/smiles/ModelPruning/Flower102/test'
#     path = '/home/smiles/ModelPruning/Flower102/test/44/image_07150.jpg'
#     label_id = class_to_idx[path.split('/')[-2]]
#     img, null = dataset.get_single_img(root, path, train=False)
#     inputVariable = Variable(img)
#     model.eval()
#     output = model(inputVariable)
#     pred_label = output.data.max(1)[1]
#     print "true label is: ",label_id
#     print "pred label is: ",pred_label.numpy()[0]