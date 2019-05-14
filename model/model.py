import torch
import torch.nn as nn
from generators import UNetGenerator
from discriminators import Discriminator
from losses import CategoryLoss, BinaryLoss

class Zi2ZiModel:
    def __init__(self, input_nc=3 ,embedding_num = 40, ngf=64, ndf=64, Lconst_penalty=15, Lcategory_penalty=1,L1_penalty=100, lr=0.001):
        self.G = UNetGenerator(input_nc=input_nc, embedding_num=embedding_num, ngf=ngf)
        self.D = Discriminator(input_nc=2*input_nc, embedding_num=embedding_num, ndf=ndf)
        self.category_loss = CategoryLoss(embedding_num)
        self.real_binary_loss = BinaryLoss(True)
        self.fake_binary_loss = BinaryLoss(False)
        self.l1_loss = nn.L1Loss()
        self.mse = nn.MSELoss()
        self.sigmoid = nn.Sigmoid()
        self.Lconst_penalty = Lconst_penalty
        self.Lcategory_penalty = Lcategory_penalty
        self.L1_penalty = L1_penalty

        self.optimizer_G = torch.optim.Adam(self.G.parameters(), lr=lr, betas=(0.5, 0.999))
        self.optimizer_D = torch.optim.Adam(self.D.parameters(), lr=lr, betas=(0.5, 0.999))

    def set_input(self, labels, real_A, real_B):
        self.real_A = real_A
        self.real_B = real_B
        self.labels = labels

    def forward(self):
        real_A = self.real_A
        real_B = self.real_B

        self.fake_B, self.encoded_real_A = self.G(self.labels, self.real_A)

        real_AB = torch.cat(real_A, real_B, 1)
        fake_AB = torch.cat(real_A, self.fake_B, 1)

        self.real_D_logits, self.real_category_logits = self.D(real_AB)
        self.fake_D_logits, self.fake_category_logits = self.D(fake_AB)

        self.real_D = self.sigmoid(self.real_D_logits)
        self.fake_D = self.sigmoid(self.fake_D_logits)

        self.encoded_fake_B = self.G.encoder(self.fake_B).view(self.fake_B.shape[0], -1)
    
    def backward_D(self, no_target_source=False):
        
        real_category_loss = self.category_loss(self.real_category_logits, self.labels)
        fake_category_loss = self.category_loss(self.fake_category_logits, self.labels)

        category_loss = (real_category_loss + fake_category_loss) * self.Lcategory_penalty
        d_loss_real = self.real_binary_loss(self.real_D_logits)
        d_loss_fake = self.fake_binary_loss(self.fake_D_logits)

        d_loss = d_loss_real + d_loss_fake + category_loss / 2.0
        d_loss.backward()
        
    
    def backward_G(self, no_target_source=False):

        const_loss = self.mse(self.encoded_real_A, self.encoded_fake_B)
        l1_loss = self.L1_penalty * self.l1_loss(self.fake_B, self.real_B)
        fake_category_loss = self.category_loss(self.fake_category_logits, self.labels)
        cheat_loss = self.real_binary_loss(self.fake_D_logits)
        
        g_loss = cheat_loss + l1_loss + self.Lcategory_penalty * fake_category_loss + const_loss
        g_loss.backward()

    def optimize_parameters(self):
        self.forward()                   # compute fake images: G(A)
        # update D
        self.set_requires_grad(self.D, True)  # enable backprop for D
        self.optimizer_D.zero_grad()     # set D's gradients to zero
        self.backward_D()                # calculate gradients for D
        self.optimizer_D.step()          # update D's weights
        # update G
        self.set_requires_grad(self.D, False)  # D requires no gradients when optimizing G
        self.optimizer_G.zero_grad()        # set G's gradients to zero
        self.backward_G()                   # calculate graidents for G
        self.optimizer_G.step()             # udpate G's weights

    def set_requires_grad(self, nets, requires_grad=False):
        """Set requies_grad=Fasle for all the networks to avoid unnecessary computations
        Parameters:
            nets (network list)   -- a list of networks
            requires_grad (bool)  -- whether the networks require gradients or not
        """
        if not isinstance(nets, list):
            nets = [nets]
        for net in nets:
            if net is not None:
                for param in net.parameters():
                    param.requires_grad = requires_grad
