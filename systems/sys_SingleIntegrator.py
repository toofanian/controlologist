from  .sys_Parents import ControlAffineSys
import numpy as np
from typing import Tuple,Union,Optional
        
class singleIntegrator(ControlAffineSys):
    def __init__(self) -> None:
        xDims = 2
        xBounds = np.array([[-3,3],[-3,3]])

        uDims = 1
        uBounds = np.array([[-100,100]])

        super().__init__(xDims=xDims,xBounds=xBounds,uDims=uDims,uBounds=uBounds)

    def f(self, t:float, x:np.ndarray) -> np.ndarray:
        f = np.array([[x[1,0]],[0]])
        return f

    def g(self, t:float, x:np.ndarray) -> np.ndarray:
        g = np.array([[0],[1]])
        return g

    def w(self, t:float, x:np.ndarray) -> np.ndarray:
        w = np.zeros((2,1))
        return w

    def xdot(self, t:float, x:np.ndarray, u:np.ndarray, noise:bool=True) -> Tuple[np.ndarray,np.ndarray,np.ndarray]:
        f = self.f(t,x)
        g = self.g(t,x)
        w = self.w(t,x)
        if noise == False: w = np.zeros(w.shape)
        return f + g@u + w

    def modify_ubounds(self,uBounds:np.ndarray):
        self.uBounds = uBounds