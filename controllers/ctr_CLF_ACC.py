import numpy as np
import cvxpy as cp

from typing import Tuple,Optional,Union
from numpy import ndarray

from .ctr_Parents           import Controller
from systems.sys_Parents    import ControlAffineSys


class Controller_CLF_ACC(Controller): 
    # BUG works with no friction, but is just under desired speed with friction.
    def __init__(self, sys:ControlAffineSys) -> None:
        super().__init__(sys=sys)
        self.makeProblem_CLFQP()
    
    def u(self,x:ndarray,t:Optional[float]=None) -> ndarray:
        self.u_ref_param.value = np.array([[0.]])
        self.r_penalty_param.value = np.array([1000000.])
        clf_val,clf_grad = self.clf(x)
        self.V_param.value = np.array([clf_val])
        self.LfV_param.value = clf_grad@self.sys.f(0,x)
        self.LgV_param.value = clf_grad@self.sys.g(0,x)
        self.problem.solve()
        return self.u_var.value

    def clf(self, x:np.ndarray) -> Tuple[float,np.ndarray]:
        return ((x[0,0]-self.sys.vdes)**2)/2, \
               np.array([[x[0,0]-self.sys.vdes,0]])
    
    def makeProblem_CLFQP(self):
        '''
        sets up the CLFQP, and returns it as a differentiable cvxpylayer

        currently hardcoded for inverted pendulum dynamics
        '''
        ### define objective
        self.u_var = cp.Variable((self.sys.uDims,1))
        self.r_var = cp.Variable(1,nonneg=True)
        self.u_ref_param = cp.Parameter((self.sys.uDims,1))
        self.r_penalty_param = cp.Parameter(1,nonneg=True)

        objective_expression = cp.sum_squares(self.u_var - self.u_ref_param) + cp.multiply(self.r_var,self.r_penalty_param)
        objective = cp.Minimize(objective_expression)

        ### define constraints
        constraints = []
        # control constraints
        for i in range(self.sys.uDims):
            constraints.append(self.u_var >= self.sys.uBounds[i,0])
            constraints.append(self.u_var <= self.sys.uBounds[i,1])

        # CLF constraints
        self.V_param = cp.Parameter(1,nonneg=True) 
        self.LfV_param =  cp.Parameter((1,1))
        self.LgV_param = cp.Parameter((1,self.sys.uDims))
        c = 1
        constraints.append(self.LfV_param + self.LgV_param@self.u_var + c*self.V_param - self.r_var <= 0)

        ### assemble problem
        self.problem = cp.Problem(objective,constraints)
        assert self.problem.is_dpp(), 'Problem is not DPP'
        assert self.problem.is_qp(), 'Problem is not QP'