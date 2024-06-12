#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: Apache Software License
import logging
import os
import random
import time
from typing import List, Union
from xmlrpc.client import Binary
from xmlrpc.client import ServerProxy

from funnylog import logger
import easyprocess

from youqu_imagecenter_rpc.install_depends import install_depends

install_depends()

import pyscreenshot
from PIL import Image

from youqu_imagecenter_rpc.conf import conf



class TemplateElementNotFound(BaseException):
    """通过模板资源未匹配到对应元素"""

    def __init__(self, *name):
        """
        通过模板资源未匹配到对应元素
        :param name: 命令
        """
        err = f"通过图片资源, 未在屏幕上匹配到元素"
        template = [f"{i}" for i in name]
        BaseException.__init__(self, err, *template)


class TemplatePictureNotExist(BaseException):
    """图片资源，文件不存在"""

    def __init__(self, name):
        """
        文件不存在
        :param name: 命令
        """
        err = f"图片资源：{name} 文件不存在!"
        logger.error(err)
        BaseException.__init__(self, err)


class ImageCenter:
    """图像识别的工具类"""

    wayland_screen_dbus = "qdbus org.kde.KWin /Screenshot screenshotFullscreen"

    @classmethod
    def _match_image_by_opencv(
            cls,
            image_path: str,
            rate: float = None,
            multiple: bool = False,
            picture_abspath: str = None,
            screen_bbox: List[int] = None,
            log_level: str = "info",
            network_retry: int = 1,
    ):
        """
         图像识别，匹配小图在屏幕中的坐标 x, y，当前仅支持1个主屏幕，如果存在多个屏幕只会截取主屏幕内容。
        :param image_path: 图像识别目标文件的存放路径,仅支持英文文件名，不支持中文文件名
        :param rate: 匹配度
        :param multiple: 是否返回匹配到的多个目标
        :param picture_abspath: 大图，默认大图是截取屏幕，否则使用传入的图片；
        :param screen_bbox: 截取屏幕上指定区域图片（仅支持X11下使用）；
            [x, y, w, h]
            x: 左上角横坐标；y: 左上角纵坐标；w: 宽度；h: 高度；根据匹配度返回坐标
        :param network_retry: 连接服务器重试次数
        """
        # pylint: disable=I1101,E1101
        if rate is None:
            rate = float(conf.IMAGE_RATE)
        screen = conf.SCREEN_CACHE

        if not picture_abspath:
            if screen_bbox:
                screen = cls.save_temporary_picture(*screen_bbox) + ".png"
            else:
                if conf.IS_LINUX:
                    if conf.IS_X11:
                        try:
                            pyscreenshot.grab().save(screen)
                        except easyprocess.EasyProcessError:
                            ...
                    else:
                        # conf.IS_WAYLAND
                        screen = os.popen(cls.wayland_screen_dbus).read().strip("\n")
                else:
                    # conf.IS_WINDOWS or conf.IS_MACOS:
                    # for windows and macos
                    pyscreenshot.grab().save(screen)

        else:
            screen = picture_abspath

        template_path = ""
        image_path = os.path.expanduser(image_path)
        # 如果传入的image_path参数不带文件后缀名，就根据文件类型判断文件是否存在，存在则将后缀类型（'.png','.jpg','.jpeg'）加上
        if not image_path.endswith(('.png', '.jpg', '.jpeg')):
            if os.path.exists(f"{image_path}.png"):
                template_path = f"{image_path}.png"
            elif os.path.exists(f"{image_path}.jpg"):
                template_path = f"{image_path}.jpg"
            elif os.path.exists(f"{image_path}.jpeg"):
                template_path = f"{image_path}.jpeg"
            else:
                logger.warning(f"The image format is not supported. Please confirm your image_path again")
        else:
            # image_path参数带有后缀名，不做任何添加
            template_path = image_path
        if not template_path:
            raise ValueError
        server = ServerProxy(f"http://{conf.SERVER_IP}:{conf.PORT}", allow_none=True)
        screen_rb = open(screen, "rb")
        template_rb = open(template_path, "rb")
        for _ in range(network_retry + 1):
            try:
                screen_path = server.image_put(Binary(screen_rb.read()))
                screen_rb.close()
                tpl_path = server.image_put(Binary(template_rb.read()))
                template_rb.close()
                return server.match_image_by_opencv(
                    tpl_path, screen_path, rate, multiple
                )
            except OSError as exc:
                raise EnvironmentError(
                    f"OCR 服务器链接失败. http://{conf.SERVER_IP}:{conf.PORT}"
                ) from exc

    @classmethod
    def find_image(
            cls,
            *widget,
            rate: Union[float, int] = None,
            multiple: bool = False,
            picture_abspath: str = None,
            screen_bbox: List[int] = None,
            log_level: str = "info",
            network_retry: int = None,
            pause: [int, float] = None,
            timeout: [int, float] = None,
            max_match_number: int = None,
    ):
        """
         在屏幕中区寻找小图，返回坐标，
         如果找不到，根据配置重试次数，每次间隔1秒
        :param picture_abspath:
        :param widget: 模板图片路径
        :param rate: 相似度
        :param multiple: 是否返回匹配到的多个目标
        :param screen_bbox: 截取屏幕上指定区域图片（仅支持X11下使用）；
            [x, y, w, h]
            x: 左上角横坐标；y: 左上角纵坐标；w: 宽度；h: 高度；根据匹配度返回坐标
        :param log_level: 日志级别
        :param network_retry: 连接服务器重试次数
        :param pause: 图像识别重试的间隔时间
        :param timeout: 最大匹配超时,单位秒
        :param max_match_number: 最大匹配次数
        :return: 坐标元组
        """
        network_retry = network_retry if network_retry else conf.NETWORK_RETRY
        pause = pause if pause else conf.PAUSE
        timeout = timeout if timeout else conf.TIMEOUT
        max_match_number = max_match_number if max_match_number else conf.MAX_MATCH_NUMBER

        retry_number = int(max_match_number)
        if retry_number < 0:
            raise ValueError("重试次数不能小于0")

        if rate is None:
            rate = float(conf.IMAGE_RATE)
        try:
            for element in widget:
                start_time = time.time()
                for _ in range(retry_number + 1):
                    locate = cls._match_image_by_opencv(
                        element,
                        rate,
                        multiple=multiple,
                        picture_abspath=picture_abspath,
                        screen_bbox=screen_bbox,
                        log_level=log_level,
                        network_retry=network_retry,
                    )
                    if not locate:
                        time.sleep(int(pause))
                    else:
                        return locate
                    end_time = time.time()
                    if end_time - start_time > timeout:
                        break
            raise TemplateElementNotFound(*widget)
        except Exception as exc:
            raise exc

    @staticmethod
    def find_image_color(widget):
        """
         获取图片的颜色值
        :param widget: 模板图片路径
        :return: 图片的颜色值
        """
        try:
            if not os.path.exists(widget):
                raise TemplatePictureNotExist(widget)
            _color = []
            with Image.open(widget) as image:
                pix = image.load()
                width = image.size[0]
                height = image.size[1]
                for _x in range(width):
                    for _y in range(height):
                        _r, _g, _b = pix[_x, _y]
                        _color.append((_r, _g, _b))
            return _color
        except Exception as exc:
            raise exc

    @classmethod
    def img_exists(cls, widget, rate=None):
        """
         判断图片是否存在，通常用于断言
        :param widget: 模块图片路径
        :param rate: 相似度
        :return:
        """
        if rate is None:
            rate = float(conf.IMAGE_RATE)
        try:
            return bool(cls.find_image(widget, rate=rate))
        # pylint: disable=broad-except
        except TemplateElementNotFound as exc:
            logger.warning(exc)
            return False

    @staticmethod
    def get_pic_px(pic_position):
        """
        获取图片的分辨率
        :param pic_position: 图片路径
        """
        return Image.open(os.path.expanduser(pic_position)).size

    @classmethod
    def get_during(
            cls,
            image_path: str,
            screen_time: Union[float, int],
            rate: float = None,
            pause: Union[int, float] = None,
            max_range: int = 10000,
    ):
        """
        在一段时间内截图多张图片进行识别，其中有一张图片识别成功即返回结果;
        适用于气泡类的断言，比如气泡在1秒内消失，如果用常规的图像识别则有可能无法识别到；
        :param image_path: 要识别的模板图片；
        :param screen_time: 截取屏幕图片的时间，单位秒；
        :param rate: 识别率；
        :param pause: 截取屏幕图片的间隔时间，默认不间隔；
        """
        during_path = "/tmp/youqu_during"
        os.system(f"rm -rf {during_path}")
        os.makedirs(during_path)
        pics = []
        start_time = time.time()
        for i in range(max_range):
            pic_name = f"{during_path}/{time.time()}_{i}.png"
            pics.append(pic_name)
            pyscreenshot.grab().save(pic_name)
            if time.time() - start_time >= screen_time:
                break
            if pause:
                time.sleep(pause)
        if not pics:
            raise ValueError
        for pic_path in pics:
            res = cls._match_image_by_opencv(
                image_path, rate=rate, picture_abspath=pic_path
            )
            if res:
                return res
        raise TemplateElementNotFound(image_path)


class ImageCenterByRGB:
    """
    By sliding and comparing the RGB values of small image and large image,
    locate the position of small image in large image.Some pre matching
    techniques are used to improve the speed.
    """

    @staticmethod
    def _check_match(_x, _y, small, bdata, sdata, rate):
        """
        Matching degree of small graph and large graph matching
        """
        same = 0
        diff = 0
        for i in range(small.width):
            for j in range(small.height):
                if bdata[_x + i, _y + j] == sdata[i, j]:
                    same = same + 1
                else:
                    diff = diff + 1
        similarity = same / (same + diff)
        return similarity >= rate

    @staticmethod
    def _pre_random_point(small):
        """
        Pre matching, take 10-20 points at random each time,
        and take coordinates randomly in the small graph
        """
        point_list = []
        count = random.randrange(10, 20)
        for _ in range(count):
            s_x = random.randrange(0, small.width)
            s_y = random.randrange(0, small.height)
            point_list.append([s_x, s_y])
        return point_list

    @staticmethod
    def _pre_random_match(_x, _y, point_list, bdata, sdata, rate):
        """
        In the small graph, several points are randomly
        selected for matching, and the matching degree is
        also set for the random points
        """
        same = 0
        diff = 0
        for point in point_list:
            if bdata[_x + point[0], _y + point[1]] == sdata[point[0], point[1]]:
                same = same + 1
            else:
                diff = diff + 1
        return same / (same + diff) >= rate

    @classmethod
    def image_center_by_rgb(cls, image_name=None, image_path=None, rate=conf.IMAGE_RATE):
        """
        By comparing the RGB values of the small image with the large
        image on the screen, the coordinates of the small image on
        the screen are returned.
        """
        if not image_path:
            image_path = conf.PIC_PATH
        small = Image.open(os.path.join(image_path, f"{image_name}.png"))
        sdata = small.load()
        big = pyscreenshot.grab()
        bdata = big.load()
        point_list = cls._pre_random_point(small)
        for _x in range(big.width - small.width):
            for _y in range(big.height - small.height):
                if cls._pre_random_match(_x, _y, point_list, bdata, sdata, rate):
                    if cls._check_match(_x, _y, small, bdata, sdata, rate):
                        return int(_x + small.width / 2), int(_y + small.height / 2)
        return False
