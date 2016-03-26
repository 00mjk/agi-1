package io.agi.framework.persistence.models;

import io.agi.framework.Node;

/**
 * Created by dave on 17/02/16.
 */
public class ModelNode {

    public String _key;
    public String _host;
    public int _port;

    public ModelNode( String key, String host, int port ) {
        _key = key;
        _host = host;
        _port = port;
    }

    public ModelNode( Node n ) {
        _key = n.getName();
        _host = n.getHost();
        _port = n.getPort();
    }

}