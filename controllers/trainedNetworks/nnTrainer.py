import torch
import torch.nn as nn
import numpy as np
import cvxpy as cp
from cvxpylayers.torch import CvxpyLayer
from torch.utils.data import Dataset,DataLoader


from systems.sys_Parents import ControlAffineSys


class nCLF(nn.Module):
    def  __init__(self,
                  x_dims,
                  hidden_size:int=64,
                  hidden_layers:int=2) -> None:
        super().__init__()

        layers = []
        # BUG: assumes at least 1 hidden layer
        layers.append(nn.Linear(x_dims,hidden_size)) 
        layers.append(nn.ReLU())
        for _ in range(hidden_layers-1):
            layers.append(nn.Linear(hidden_size,hidden_size))
            layers.append(nn.ReLU())
        layers.append(nn.Linear(hidden_size,1))

        self.stack_mlp = nn.Sequential(*layers)

    def forward(self,x):
        return self.stack_mlp(x)**2 # TODO squared to enforce pos def, but is there a better way to do this?


class dataset_UniformStates(Dataset):
    '''
    dataset of num_samples state sample, pulled uniformly from within xBounds. Samples are by column.
    '''
    def __init__(self,xBounds:np.ndarray,num_samples:int):
        self.data = np.random.uniform(low=xBounds[:,0],high=xBounds[:,1],size=(num_samples,xBounds.shape[0])).T

    def __len__(self) -> int:
        return self.data.shape[1]

    def __getitem__(self, idx:int) -> np.ndarray:
        return self.data[:,idx]


class train_nCLF():
    def __init__(self,
                 sys:ControlAffineSys) -> None:

        self.sys:ControlAffineSys = sys()
        self.network = nCLF(self.sys.xDims)
        self.clfqp_layer = self._makeProblem_CLFQP_layer()

    def train(self):
        num_samples = 5000
        dataset = dataset_UniformStates(xBounds=self.sys.xBounds,num_samples=num_samples)
        dataloader = DataLoader(dataset=dataset,batch_size=1,shuffle=True)
        # TODO allow batch > 1. currently bottlenecked at qp.

        optimizer = torch.optim.Adam(self.network.parameters(),lr=.003)

        lagrange_atzero = 10.
        lagrange_relax = 100

        epochs = 10
        for epoch in range(epochs):
            clf_val_atzero:torch.Tensor = self.network(torch.zeros((self.sys.xDims,1)).float())
            assert clf_val_atzero >= 0

            loss = torch.zeros((1))
            loss += lagrange_atzero*clf_val_atzero

            for i,x in enumerate(dataloader):

                f = self.sys.f(0,x)
                g = self.sys.g(0,x)

                x_ten = torch.tensor(x,requires_grad=True)
                clf_value_ten:torch.Tensor = self.network(x_ten.float())
                clf_value_ten.backward()

                clf_value_ten = clf_value_ten
                LfV_ten = (x_ten.grad@f).type_as(clf_value_ten)
                LgV_ten = (x_ten.grad@g).type_as(clf_value_ten)

                u_ref = torch.zeros((self.sys.uDims,1),dtype=torch.float32)
                relax_penalty = torch.tensor([100.],dtype=torch.float32)
                
                params = [u_ref,relax_penalty,clf_value_ten,LfV_ten,LgV_ten]
                u,r = self.clfqp_layer(*params)

                assert r >= 0, f'r is negative: {r}'

                loss += lagrange_relax/num_samples * r
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        
            if loss <= .05: break
        torch.save(self.network,'trainedNetworks/trainedCLF.pth')
        pass


    def _makeProblem_CLFQP_layer(self):
        '''
        sets up the CLFQP, and returns it as a differentiable cvxpylayer
        '''
        ### define variables and parameters
        self.u_var = cp.Variable((self.sys.uDims,1))
        self.u_ref_param = cp.Parameter((self.sys.uDims,1))
        self.r_var = cp.Variable(1,nonneg=True)
        self.r_penalty_param = cp.Parameter(1,nonneg=True)
        self.V_param = cp.Parameter(1,nonneg=True) 
        self.LfV_param =  cp.Parameter(1)
        self.LgV_param = cp.Parameter((1,self.sys.uDims))
        c = 1 # hyperparameter, should be tied to one used during training

        ### define objective
        objective_expression = cp.sum_squares(self.u_var - self.u_ref_param) + cp.multiply(self.r_var,self.r_penalty_param)
        objective = cp.Minimize(objective_expression)

        ### define constraints
        constraints = []
        # control constraints
        for iu in range(self.sys.uDims):
            constraints.append(self.u_var[iu] >= self.sys.uBounds[iu,0])
            constraints.append(self.u_var[iu] <= self.sys.uBounds[iu,1])
        # CLF constraint
        constraints.append(self.LfV_param + self.LgV_param@self.u_var <= -c*self.V_param + self.r_var)

        ### assemble problem
        problem = cp.Problem(objective,constraints)
        assert problem.is_dpp(), 'Problem is not dpp'

        # convert to differentiable layer, store in self for later use
        variables = [self.u_var,self.r_var]
        parameters = [self.u_ref_param,self.r_penalty_param,self.V_param,self.LfV_param,self.LgV_param]
        problem_layer = CvxpyLayer(problem=problem,parameters=parameters,variables=variables)
        
        return problem_layer


    


if __name__ == '__main__':
    
    trainer = train_nCLF()