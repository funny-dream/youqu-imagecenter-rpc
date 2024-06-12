from youqu_imagecenter_rpc import ImageCenter
from youqu_imagecenter_rpc.conf import conf

conf.SERVER_IP = '10.8.11.139'

a = ImageCenter.find_image("~/Desktop/2.png")
print(a)
