# %% [code]

import torch
import torch.nn as nn
from torchvision import transforms

from sklearn.metrics import top_k_accuracy_score
import numpy as np

device = 'cuda' if torch.cuda.is_available() else 'cpu'



xception_train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomAffine(degrees=15, translate= (.15, .15), scale = (0.85, 1.15)),

    transforms.Resize(324), #Resize data to be 224x224.
    transforms.RandomCrop(299),
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
])

xception_test_transform = transforms.Compose([
    transforms.Resize((324, 324)),
    transforms.TenCrop((299, 299)),
    transforms.Lambda(lambda crops: torch.stack([transforms.ToTensor()(crop) for crop in crops])),
    transforms.Lambda(lambda crops: torch.stack([transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))(x) for x in crops]))
    ])

train_transform = xception_train_transform
test_transform = xception_test_transform

resnet_train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomAffine(degrees=15, translate= (.15, .15), scale = (0.85, 1.15)),

    transforms.Resize(256), #Resize data to be 224x224.
    transforms.RandomCrop(224),
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
])


resnet_test_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.TenCrop((224, 224)),
    transforms.Lambda(lambda crops: torch.stack([transforms.ToTensor()(crop) for crop in crops])),
    transforms.Lambda(lambda crops: torch.stack([transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))(x) for x in crops]))
    ])


@torch.no_grad()
def print_test_details(model:nn.Module, loss, test_loader:torch.utils.data.DataLoader):

    model.eval()

    top_1_correct = 0
    top_5_correct = 0
    total_loss = 0
    

    i = 0
    for test_features_batch, test_labels_batch in iter(test_loader):
        i+=1
        if (i%100)==0:
            print(i)


        # original_image_label = test_labels_batch[0].to(device)
        num_current_original_samples = test_labels_batch.size(0)

        bs, n_crops, c, h, w = test_features_batch.shape
        test_features_flat = test_features_batch.view(-1, c, h, w).to(device)
        crop_outputs = model(test_features_flat)
            
        averaged_outputs_batch = crop_outputs.view(bs, n_crops, -1).mean(dim=1)

        loss_val = loss(averaged_outputs_batch, test_labels_batch.to(device))
        total_loss += loss_val.item() * num_current_original_samples
            
        all_possible_labels = np.array(range(averaged_outputs_batch.shape[1]))
            
        cpu_labels = test_labels_batch.cpu().numpy()
        cpu_averaged_outputs = averaged_outputs_batch.cpu().numpy()

        top_1_correct += top_k_accuracy_score(cpu_labels, cpu_averaged_outputs, k=1, labels=all_possible_labels, normalize=False)
        top_5_correct += top_k_accuracy_score(cpu_labels, cpu_averaged_outputs, k=5, labels=all_possible_labels, normalize=False)
            
        


    top_1_accuracy = top_1_correct/len(test_loader.dataset)
    top_5_accuracy = top_5_correct/len(test_loader.dataset)
    loss_value = total_loss/len(test_loader.dataset)

    print(f"Test Score - Loss: {loss_value}, top-1 accuracy: {top_1_accuracy}, top-5 accuracy: {top_5_accuracy}")

    return (loss_value, top_1_accuracy, top_5_accuracy)



## FUNCTION FOR RESNET

def conv3x3(in_channels:int, out_channels:int, stride:int=1, padding:int=1):
    return nn.Conv2d(
        in_channels=in_channels, 
        out_channels=out_channels, 
        kernel_size=3,
        padding=padding,
        stride=stride,
        bias=False
    )

def conv1x1(in_channels:int, out_channels:int, stride:int=1):
    return nn.Conv2d(
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=1,
        padding=0,
        stride=stride,
        bias=False
    )




class BasicBlock(nn.Module):
    expansion = 1
    def __init__(
            self,
            in_channels:int,
            out_channels:int,
            stride:int=1,

    ):
        super().__init__()

        self.conv1 = conv3x3(in_channels=in_channels, out_channels=out_channels, stride=stride)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

        self.conv2 = conv3x3(in_channels=out_channels, out_channels=out_channels)
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.downsample = None
        if (in_channels!=out_channels) or (stride!=1):
            self.downsample = nn.Sequential(
                conv1x1(in_channels=in_channels, out_channels=out_channels, stride=stride),
                nn.BatchNorm2d(out_channels)
            )
    
    def forward(self, X):
        
        identity = X

        output = self.conv1(X)
        output = self.bn1(output)
        output = self.relu(output)

        output = self.conv2(output)
        output = self.bn2(output)

        if self.downsample:
            identity = self.downsample(identity)
        
        output += identity
        output = self.relu(output)

        return output


class BottleNeck(nn.Module):
    expansion = 4
    """
    """

    def __init__(self, in_channels:int, out_channels:int, stride:int=1):
        """
        out_channels: the number of output channels for the 1st and 2nd layer.

        final output will have `expansion*out_channels` channels
        """
        super().__init__()

        

        final_output_channels = self.expansion * out_channels


        self.conv1 = conv1x1(in_channels=in_channels, out_channels=out_channels, stride=1)
        self.bn1 = nn.BatchNorm2d(num_features=out_channels)
        
        self.conv2 = conv3x3(in_channels=out_channels, out_channels=out_channels, stride=stride)
        self.bn2 = nn.BatchNorm2d(num_features=out_channels)

        self.conv3 = conv1x1(in_channels=out_channels, out_channels=final_output_channels, stride=1)
        self.bn3 = nn.BatchNorm2d(num_features=final_output_channels)

        self.downsample = None

        if final_output_channels!=in_channels or stride!=1:
            self.downsample = nn.Sequential(
                conv1x1(in_channels, final_output_channels, stride=stride),
                nn.BatchNorm2d(final_output_channels)
            )

        self.relu = nn.ReLU(inplace=True)
        
    def forward(self, X):

        identity = X

        out = self.conv1(X)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample:
            identity = self.downsample(identity)

        out += identity

        return out



class ResNet(nn.Module):
    def __init__(
        self,
        block,
        layers,
        num_classes: int = 256,
        dropout:float=0.
    ) -> None:
        
        super().__init__()
        
        self.in_channels = 64

        self.conv1 = nn.Conv2d(3, self.in_channels, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(self.in_channels)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
        self.dropout = nn.Dropout(p=dropout)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        
        self.fc = nn.Linear(512 * block.expansion, num_classes)


        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)


    def _make_layer(
        self,
        block:BottleNeck,
        out_planes: int,
        blocks: int,
        stride: int = 1,
    ) -> nn.Sequential:

        

        layers = []
        layers.append(
            block(in_channels=self.in_channels, out_channels=out_planes, stride=stride)
        )

        self.in_channels = out_planes*block.expansion
        
        for _ in range(1, blocks):
            layers.append(
                block(
                    self.in_channels,
                    out_planes,
                    stride=1
                )
            )

        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.dropout(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)

        return x



## FUNCTIONS FOR XCEPTION 

class BNConv2D(nn.Module):

    def __init__(
            self,
            in_channels: int,
            out_channels: int,
            kernel_size: int,
            stride = 1,
            padding= 0,
            dilation=1,
            groups=1,
    ):
        super().__init__()

        self.conv = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            groups=groups,
            bias=False
        )
        self.bn = nn.BatchNorm2d(out_channels)


    def forward(self, X):
        
        out = self.conv(X)
        out = self.bn(out)

        return out
    
class BN_DepthwiseSeparableConv2D(nn.Module):

    def __init__(
            self,
            in_channels: int,
            out_channels: int,
            kernel_size: int,
            stride = 1,
            padding= 0,
            dilation=1,
    ):
        super().__init__()

        self.depthwise_conv = nn.Conv2d(
            in_channels=in_channels,
            out_channels=in_channels, 
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            groups=in_channels,
            bias=False
        )
        self.pointwise_conv = nn.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=1,
            bias=False
        )
        self.bn = nn.BatchNorm2d(out_channels)
    
    def forward(self, X):

        out = self.depthwise_conv(X)
        out = self.pointwise_conv(out)
        out = self.bn(out)

        return out

class MiddleFlow(nn.Module):

    def __init__(self, channels:int=512):
        super().__init__()

        self.flow = nn.Sequential(
            nn.ReLU(), BN_DepthwiseSeparableConv2D(channels, channels, 3, 1, 1),
            nn.ReLU(), BN_DepthwiseSeparableConv2D(channels, channels, 3, 1, 1),
            nn.ReLU(), BN_DepthwiseSeparableConv2D(channels, channels, 3, 1, 1)
        )

    def forward(self, X):

        out = self.flow(X)
        out += X
        return out

class Xception(nn.Module):
    """
    [paper](https://arxiv.org/pdf/1610.02357) from where this is implemented
    """

    def __init__(self, num_middle_layers:int=3, dropout:float=0.):
        super().__init__()


        ## ENTRY FLOW
        self.block1_conv1 = BN_DepthwiseSeparableConv2D(in_channels=3, out_channels=32, stride=2, kernel_size=3)
        self.block1_conv2 = BN_DepthwiseSeparableConv2D(in_channels=32, out_channels=64, kernel_size=3)
        

        self.residual1 = BNConv2D(in_channels=64, out_channels=128, kernel_size=1, padding=0, stride=2)
        self.residual2 = BNConv2D(in_channels=128, out_channels=256, kernel_size=1, padding=0, stride=2)
        self.residual3 = BNConv2D(in_channels=256, out_channels=512, kernel_size=1, padding=0, stride=2)


        self.block2_conv1 = BN_DepthwiseSeparableConv2D(in_channels=64, out_channels=128, kernel_size=3, padding=1)
        self.block2_conv2 = BN_DepthwiseSeparableConv2D(in_channels=128, out_channels=128, kernel_size=3, padding=1)
        

        self.block3_conv1 = BN_DepthwiseSeparableConv2D(in_channels=128, out_channels=256, kernel_size=3, padding=1)
        self.block3_conv2 = BN_DepthwiseSeparableConv2D(in_channels=256, out_channels=256, kernel_size=3, padding=1)

        self.block4_conv1 = BN_DepthwiseSeparableConv2D(in_channels=256, out_channels=256, kernel_size=3, padding=1)
        self.block4_conv2 = BN_DepthwiseSeparableConv2D(in_channels=256, out_channels=512, kernel_size=3, padding=1)


        
        ## MIDDLE FLOW
        channels = 512

        self.middle_layers = nn.ModuleList()

        for _ in range(num_middle_layers):
            
            self.middle_layers.append(MiddleFlow(channels=channels))


        ## EXIT FLOW


        self.exitblock1_conv1 = BN_DepthwiseSeparableConv2D(channels, 728, 3, padding=1)
        self.exitblock1_conv2 = BN_DepthwiseSeparableConv2D(728, 1024, 3, padding=1)





        self.last = nn.Linear(1024, 256)
        

        
        self.global_avgpool = nn.AdaptiveAvgPool2d(1)
        self.max_pooling = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.relu = nn.ReLU()

        self.dropout = nn.Dropout(p=dropout)


    def forward(self, X):

        #block 1
        out = self.block1_conv1(X)
        out = self.relu(out)
        out = self.block1_conv2(out)
        out = self.relu(out)
        
        #block 2
        residual = self.residual1(out)

        out = self.block2_conv1(out)
        out = self.relu(out)
        out = self.block2_conv2(out)
        out = self.max_pooling(out)

        out += residual
        
        #block 3
        residual = self.residual2(out)

        out = self.relu(out)
        out = self.block3_conv1(out)
        out = self.relu(out)
        out = self.block3_conv2(out)
        out = self.max_pooling(out)

        out += residual

        #block 4
        residual = self.residual3(out)

        out = self.relu(out)
        out = self.block4_conv1(out)
        out = self.relu(out)
        out = self.block4_conv2(out)
        out = self.max_pooling(out)

        out += residual

        #middle flow
        for layer in self.middle_layers:
            residual = out
            out = layer(out)            
            out += residual


        ## EXIT flow
        out = self.exitblock1_conv1(out)
        out = self.exitblock1_conv2(out)
        out = self.global_avgpool(out)

        out = torch.flatten(out, 1)

        out = self.dropout(out)
        out = self.last(out)


        



        return out

        