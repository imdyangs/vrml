import h5py
import random
import os
import torch
import torch.optim as optim
import torch.nn.functional as F
import torchvision.transforms as transforms

import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

from annoy import AnnoyIndex
from sklearn.manifold import TSNE

from tqdm import tqdm
from torch.autograd import Variable
from PIL import Image

from models import Generator, Encoder, Decoder, Discriminator, weight_init


def log(x):
    """ Log func to prevent nans """
    return torch.log(x + 1e-8)


class aae_worker:
    def __init__(self, z_dim=3, h_dim=128, filter_num=64, channel_num=3,
                 lr=1e-3, cuda=False):
        # Are we cuda'ing it
        self.cuda = cuda

        # Encoder, decoder, discriminator
        self.encoder = self.cudafy_(
            Encoder(z_dim, h_dim=h_dim, filter_num=filter_num,
                    channel_num=channel_num)
        )
        self.encoder.apply(weight_init)

        self.decoder = self.cudafy_(
            Decoder(z_dim, filter_num=filter_num, channel_num=channel_num)
        )
        self.decoder.apply(weight_init)

        self.discrim = self.cudafy_(Discriminator(z_dim))
        self.discrim.apply(weight_init)

        # Optimizers
        generator_params = list(self.encoder.parameters()) + \
            list(self.decoder.parameters())
        self.optim_enc = optim.Adam(self.encoder.parameters(), lr=lr)
        self.optim_dec = optim.Adam(self.decoder.parameters(), lr=lr)
        self.optim_dis = optim.Adam(self.discrim.parameters(), lr=lr)
        self.optim_gen = optim.Adam(generator_params, lr=lr)

        self.start_epoch = 0

        # z dimensions
        self.z_dim = z_dim
        self.tree = AnnoyIndex(3, metric='euclidean')
        self.h5_file = None

    def cudafy_(self, m):
        if self.cuda:
            if hasattr(m, 'cuda'):
                return m.cuda()
        return m

    def reset_gradients_(self):
        self.encoder.zero_grad()
        self.decoder.zero_grad()
        self.discrim.zero_grad()

    def train(self, loader, current_epoch):
        for idx, (features_, _) in enumerate(tqdm(loader)):
            features = features_
            features = Variable(self.cudafy_(features))

            smoothen_features = features_
            smoothen_features = Variable(self.cudafy_(smoothen_features))

            """ Decoding Phase """
            z_sample = self.encoder(smoothen_features)
            features_sample = self.decoder(z_sample)

            dec_loss = self.cudafy_(
                F.binary_cross_entropy(features_sample, features)
            )
            dec_loss.backward()
            self.optim_enc.step()
            self.optim_dec.step()
            self.reset_gradients_()

            """ Regularization phase """
            # Discriminator
            z_fake = self.encoder(smoothen_features)
            z_real = Variable(self.cudafy_(
                torch.randn(features.size(0), self.encoder.z_dim)
            ))

            discrim_fake = self.discrim(z_fake)
            discrim_real = self.discrim(z_real)

            discrim_loss = - \
                torch.mean(log(discrim_real) +
                           log(1 - discrim_fake))
            discrim_loss.backward()

            self.optim_dis.step()
            self.reset_gradients_()

            # Encoder
            z_fake = self.encoder(smoothen_features)
            discrim_fake = self.discrim(z_fake)

            enc_loss = -torch.mean(log(discrim_fake))
            enc_loss.backward()

            self.optim_enc.step()
            self.reset_gradients_()

            # Generator (Encoder + Decoder)
            gen_ = self.decoder(self.encoder(smoothen_features))
            gen_loss = torch.mean(torch.sum((gen_ - features) ** 2, 1))
            gen_loss.backward()
            self.optim_gen.step()
            self.reset_gradients_()

            tqdm.write(
                "Epoch: {}\t"
                "Decoder_Loss: {:.4f}\t"
                "Discrim_loss: {:.4f}\t"
                "Encoder_Loss: {:.4f}\t"
                "Generator Loss: {:.4f}"
                .format(
                    current_epoch, dec_loss.data[0], discrim_loss.data[0], enc_loss.data[0], gen_loss.data[0]
                )
            )

        # Gets a random image and encode it to
        # get the latent space
        self.visualize(z_fake, features, current_epoch)

    def reconstruct(self, img, transformers=None):
        if transformers is not None:
            img = transformers(img)

        img = Variable(self.cudafy_(img))
        img = img.view(1, img.size(0), img.size(1), img.size(2))

        z = self.encoder(img)
        return self.generate(z)

    def generate(self, z):
        decoded = self.decoder(z)

        if self.cuda:
            decoded = decoded.data.cpu().numpy()
        else:
            decoded = decoded.data.numpy()

        dimg = self.tensor2pil(decoded[0])

        return dimg

    def visualize(self, z, origin, e):
        """
        Visualize the training progress, for sanity checks

        Args:
            z: z space
            origin: origin image
            e: current epoch
        """
        if not os.path.exists('visualize/'):
            os.makedirs('visualize/')

        # Random image from sample
        idx = random.randint(0, z.size(0) - 1)

        # Takes z sample and converts it to range
        # 0-255
        decoded = self.decoder(z)

        if self.cuda:
            decoded = decoded.data.cpu().numpy()
            origin = origin.data.cpu().numpy()
        else:
            decoded = decoded.data.numpy()
            origin = origin.data.numpy()
        dimg = self.tensor2pil(decoded[idx])
        oimg = self.tensor2pil(origin[idx])

        fig, axarr = plt.subplots(2, sharex=True)

        axarr[0].imshow(oimg)
        axarr[0].set_title('original @ epoch: {}'.format(e))

        axarr[1].imshow(dimg)
        axarr[1].set_title('decoded @ epoch : {}'.format(e))

        fig.savefig('visualize/{}.png'.format(e))

    @staticmethod
    def tensor2pil(t):
        # Assuming t is between 0.0 - 1.0
        t = t * 255
        t = t.astype(np.uint8)
        t = np.rollaxis(t, 0, 3)
        return Image.fromarray(t, 'RGB')

    def save_(self, e, filename='aae.path.tar'):
        torch.save({
            'encoder': self.encoder.state_dict(),
            'decoder': self.decoder.state_dict(),
            'discrim': self.discrim.state_dict(),
            'epoch': e + 1
        }, 'epoch{}_{}'.format(e, filename))
        print('Saved model state')

    def load_(self, filedir):
        if os.path.isfile(filedir):
            checkpoint = torch.load(filedir)

            self.encoder.load_state_dict(checkpoint['encoder'])
            self.decoder.load_state_dict(checkpoint['decoder'])
            self.discrim.load_state_dict(checkpoint['discrim'])
            self.start_epoch = checkpoint['epoch']

            print('Model state loaded')

        else:
            print('Cant find file')

    def build_tree(self, loader):
        # only building in z_dim
        t = AnnoyIndex(3, metric='euclidean')

        h5 = h5py.File('ann_data.h5', 'w')

        images = []
        embeddings = []

        for idx, (features, _) in enumerate(tqdm(loader)):
            features = self.cudafy_(Variable(features))

            z = self.encoder(features).squeeze()
            z_np = z.data.cpu().numpy()

            images.append(list(features.data.cpu().numpy().squeeze()))
            embeddings.append(z_np)

        # TSNE it
        z = embeddings

        if self.z_dim > 3:
            z = TSNE(n_components=3).fit_transform(z_np)

        for idx, x in enumerate(tqdm(z)):
            t.add_item(idx, x)

        t.build(32)  # 32 trees
        t.save('aae.ann')

        h5.create_dataset('image', data=images)
        h5.create_dataset('coordinate', data=embeddings)

    def load_tree(self, tree_loc, h5_loc):
        self.tree.load(tree_loc)
        self.h5_file = h5py.File(h5_loc, 'r')

    def search_similar(self, coordinate):
        if self.h5_file is None:
            print('YOUR HAVENT LOAD YOUR H5 FILE')

        # Returns top 50
        ret = self.tree.get_nns_by_vector(
            coordinate, 50, include_distances=True)

        if len(ret[0]) == 0:
            print('YOUR DB IS EMPTY. YOU PROBABLY HAVENT LOAD YOUR SHIT')

        image_indexes = []
        distances = []
        coordinates = []

        for i, (idx, dis) in enumerate(zip(ret[0], ret[1])):
            img_loc = '/tmp/image{}.png'.format(i)

            # Save image
            img = self.tensor2pil(np.array(self.h5_file['image'][idx]))
            img.save(img_loc)

            image_indexes.append(idx)
            distances.append(dis)
            coordinates.append(self.h5_file['coordinate'][idx])

        return image_indexes, coordinates, distances
