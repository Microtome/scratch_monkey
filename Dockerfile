FROM fedora:latest AS builder
RUN mkdir -p /rootfs/var/home /rootfs/var/opt /rootfs/var/usrlocal /rootfs/usr && \
    ln -s usr/bin   /rootfs/bin && \
    ln -s usr/sbin  /rootfs/sbin && \
    ln -s usr/lib   /rootfs/lib && \
    ln -s usr/lib64 /rootfs/lib64 && \
    ln -s var/opt   /rootfs/opt && \
    ln -s var/home  /rootfs/home

FROM scratch
COPY --from=builder /rootfs/ /
