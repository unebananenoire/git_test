pre_start() {
  if [ -x /usr/sbin/squid ]; then
      SQUID=/usr/sbin/squid
  elif  [ -x /usr/sbin/squid3 ]; then
      SQUID=/usr/sbin/squid3
  else
      echo "No squid binary found"
      exit 1
  fi

  # ensure all cache dirs are there
  install -d -o proxy -g proxy -m 750 /var/cache/maas-proxy/
  install -d -o proxy -g proxy -m 750 /var/log/maas/proxy/
  install -m 750 -o proxy -g proxy -d /var/spool/maas-proxy/
  if [ -d /var/log/maas/proxy ]; then
   chown -R proxy:proxy /var/log/maas/proxy
  fi
  if [ ! -d /var/cache/maas-proxy/00 ]; then
   $SQUID -z -N -f /etc/maas/maas-proxy.conf
  fi
}

# from the squid3 debian init script
find_cache_dir () {
        w="     " # space tab
        res=`sed -ne '
                s/^'$1'['"$w"']\+[^'"$w"']\+['"$w"']\+\([^'"$w"']\+\).*$/\1/p;
                t end;
                d;
                :end q' < $CONFIG`
        [ -n "$res" ] || res=$2
        echo "$res"
}

