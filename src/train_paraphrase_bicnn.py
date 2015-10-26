
import cPickle
import gzip
import os
import sys
sys.setrecursionlimit(6000)
import time

import numpy
import theano
import theano.tensor as T
import theano.sandbox.neighbours as TSN

from logistic_sgd import LogisticRegression
from mlp import HiddenLayer
from WPDefined import ConvFoldPoolLayer, dropout_from_layer, shared_dataset, repeat_whole_matrix
from cis.deep.utils.theano import debug_print
from theano.tensor.signal import downsample
from theano.tensor.nnet import conv
from loadData import load_msr_corpus, load_word2vec_to_init
from word2embeddings.nn.util import zero_value, random_value_normal
from common_functions import Conv_with_input_para, Average_Pooling_for_batch1, create_conv_para




def evaluate_lenet5(learning_rate=0.055, n_epochs=2000, nkerns=[50], batch_size=1, window_width=3,
                    maxSentLength=60, emb_size=300, hidden_size=200,
                    margin=0.5, L2_weight=0.0000001, update_freq=10):
#def evaluate_lenet5(learning_rate=0.1, n_epochs=2000, nkerns=[6, 12], batch_size=70, useAllSamples=0, kmax=30, ktop=5, filter_size=[10,7],
#                    L2_weight=0.000005, dropout_p=0.5, useEmb=0, task=5, corpus=1):

    rootPath='/mounts/data/proj/wenpeng/Dataset/MicrosoftParaphrase/tokenized_msr/';
    rng = numpy.random.RandomState(23455)
    datasets, vocab_size=load_msr_corpus(rootPath+'vocab.txt', rootPath+'tokenized_train.txt', rootPath+'tokenized_test.txt', maxSentLength)
    indices_train, trainY, trainLengths, trainLeftPad, trainRightPad= datasets[0]
    indices_train_l=indices_train[::2,:]
    indices_train_r=indices_train[1::2,:]
    trainLengths_l=trainLengths[::2]
    trainLengths_r=trainLengths[1::2]
    trainLeftPad_l=trainLeftPad[::2]
    trainLeftPad_r=trainLeftPad[1::2]
    trainRightPad_l=trainRightPad[::2]
    trainRightPad_r=trainRightPad[1::2]    
    indices_test, testY, testLengths, testLeftPad, testRightPad= datasets[1]
    indices_test_l=indices_test[::2,:]
    indices_test_r=indices_test[1::2,:]
    testLengths_l=testLengths[::2]
    testLengths_r=testLengths[1::2]
    testLeftPad_l=testLeftPad[::2]
    testLeftPad_r=testLeftPad[1::2]
    testRightPad_l=testRightPad[::2]
    testRightPad_r=testRightPad[1::2]  

    n_train_batches=indices_train_l.shape[0]/batch_size
    n_test_batches=indices_test_l.shape[0]/batch_size
    
    train_batch_start=list(numpy.arange(n_train_batches)*batch_size)
    test_batch_start=list(numpy.arange(n_test_batches)*batch_size)

    
    indices_train_l=theano.shared(numpy.asarray(indices_train_l, dtype=theano.config.floatX), borrow=True)
    indices_train_r=theano.shared(numpy.asarray(indices_train_r, dtype=theano.config.floatX), borrow=True)
    indices_test_l=theano.shared(numpy.asarray(indices_test_l, dtype=theano.config.floatX), borrow=True)
    indices_test_r=theano.shared(numpy.asarray(indices_test_r, dtype=theano.config.floatX), borrow=True)
    indices_train_l=T.cast(indices_train_l, 'int32')
    indices_train_r=T.cast(indices_train_r, 'int32')
    indices_test_l=T.cast(indices_test_l, 'int32')
    indices_test_r=T.cast(indices_test_r, 'int32')
    


    rand_values=random_value_normal((vocab_size+1, emb_size), theano.config.floatX, numpy.random.RandomState(1234))
    rand_values[0]=numpy.array(numpy.zeros(emb_size))
    #rand_values[0]=numpy.array([1e-50]*emb_size)
    rand_values=load_word2vec_to_init(rand_values, rootPath+'vocab_embs_300d.txt')
    embeddings=theano.shared(value=rand_values, borrow=True)      
    
    cost_tmp=0
    error_sum=0
    
    # allocate symbolic variables for the data
    index = T.lscalar()  # index to a [mini]batch
    x_index_l = T.imatrix('x_index_l')   # now, x is the index matrix, must be integer
    x_index_r = T.imatrix('x_index_r')
    y = T.ivector('y')  
    left_l=T.iscalar()
    right_l=T.iscalar()
    left_r=T.iscalar()
    right_r=T.iscalar()
    length_l=T.iscalar()
    length_r=T.iscalar()
    #x=embeddings[x_index.flatten()].reshape(((batch_size*4),maxSentLength, emb_size)).transpose(0, 2, 1).flatten()
    ishape = (emb_size, maxSentLength)  # this is the size of MNIST images
    filter_size=(emb_size,window_width)
    #poolsize1=(1, ishape[1]-filter_size[1]+1) #?????????????????????????????
    length_after_wideConv=ishape[1]+filter_size[1]-1
    
    ######################
    # BUILD ACTUAL MODEL #
    ######################
    print '... building the model'

    # Reshape matrix of rasterized images of shape (batch_size,28*28)
    # to a 4D tensor, compatible with our LeNetConvPoolLayer
    #layer0_input = x.reshape(((batch_size*4), 1, ishape[0], ishape[1]))
    layer0_l_input = embeddings[x_index_l.flatten()].reshape((batch_size,maxSentLength, emb_size)).transpose(0, 2, 1).dimshuffle(0, 'x', 1, 2)
    layer0_r_input = embeddings[x_index_r.flatten()].reshape((batch_size,maxSentLength, emb_size)).transpose(0, 2, 1).dimshuffle(0, 'x', 1, 2)
    
    '''
    conv_W, conv_b=create_conv_para(rng, filter_shape=(nkerns[0], 1, filter_size[0], filter_size[1]))

    #layer0_output = debug_print(layer0.output, 'layer0.output')
    layer0_l = Conv_with_input_para(rng, input=layer0_l_input,
            image_shape=(batch_size, 1, ishape[0], ishape[1]),
            filter_shape=(nkerns[0], 1, filter_size[0], filter_size[1]), W=conv_W, b=conv_b)
    layer0_r = Conv_with_input_para(rng, input=layer0_r_input,
            image_shape=(batch_size, 1, ishape[0], ishape[1]),
            filter_shape=(nkerns[0], 1, filter_size[0], filter_size[1]), W=conv_W, b=conv_b)
    layer0_l_output=debug_print(layer0_l.output, 'layer0_l.output')
    layer0_r_output=debug_print(layer0_r.output, 'layer0_r.output')

    layer1=Average_Pooling_for_batch1(rng, input_l=layer0_l_output, input_r=layer0_r_output, kern=nkerns[0],
                                       left_l=left_l, right_l=right_l, left_r=left_r, right_r=right_r, 
                                       length_l=length_l+filter_size[1]-1, length_r=length_r+filter_size[1]-1,
                                       dim=maxSentLength+filter_size[1]-1)
    
    layer1_out=debug_print(layer1.output, 'layer1_out')
    
    layer2=HiddenLayer(rng, input=layer1_out, n_in=nkerns[0]*2, n_out=hidden_size, activation=T.tanh)
    '''
    sum_uni_l=T.sum(layer0_l_input, axis=3).reshape((1, emb_size))
    norm_uni_l=sum_uni_l/T.sqrt((sum_uni_l**2).sum())
    sum_uni_r=T.sum(layer0_r_input, axis=3).reshape((1, emb_size))
    norm_uni_r=sum_uni_r/T.sqrt((sum_uni_r**2).sum())
    uni_cosine=T.dot(norm_uni_l, norm_uni_r.T).reshape((1,1))
    eucli=(1-T.sqrt(T.sqr(sum_uni_l-sum_uni_r).sum())).reshape((1,1))
    len_l=length_l.reshape((1,1))
    len_r=length_r.reshape((1,1))    
    length_gap=T.log(1+(T.sqrt((len_l-len_r)**2))).reshape((1,1))
    layer3_input=T.concatenate([norm_uni_l,norm_uni_r,  uni_cosine,eucli, len_l, len_r, length_gap], axis=1)#, layer2.output, layer1.output_cosine], axis=1)
    #layer3=LogisticRegression(rng, input=layer3_input, n_in=hidden_size+emb_size*2+2, n_out=2)
    layer3=LogisticRegression(rng, input=layer3_input, n_in=emb_size*2+5, n_out=2)
    
    #L2_reg =(layer3.W** 2).sum()+(layer2.W** 2).sum()+(layer1.W** 2).sum()+(conv_W** 2).sum()
    L2_reg =(layer3.W** 2).sum()#+(layer2.W** 2).sum()+(conv_W** 2).sum()
    cost_this =layer3.negative_log_likelihood(y)+L2_weight*L2_reg
    cost=(cost_this+cost_tmp)/update_freq
    

    
    test_model = theano.function([index], [layer3.errors(y), layer3.y_pred],
          givens={
            x_index_l: indices_test_l[index: index + batch_size],
            x_index_r: indices_test_r[index: index + batch_size],
            y: testY[index: index + batch_size],
            left_l: testLeftPad_l[index],
            right_l: testRightPad_l[index],
            left_r: testLeftPad_r[index],
            right_r: testRightPad_r[index],
            length_l: testLengths_l[index],
            length_r: testLengths_r[index]}, on_unused_input='ignore')


    #params = layer3.params + layer2.params + layer1.params+ [conv_W, conv_b]
    params = layer3.params# + layer2.params + [conv_W, conv_b]
    
    accumulator=[]
    for para_i in params:
        eps_p=numpy.zeros_like(para_i.get_value(borrow=True),dtype=theano.config.floatX)
        accumulator.append(theano.shared(eps_p, borrow=True))
      
    # create a list of gradients for all model parameters
    grads = T.grad(cost, params)

    updates = []
    for param_i, grad_i, acc_i in zip(params, grads, accumulator):
        grad_i=debug_print(grad_i,'grad_i')
        acc = acc_i + T.sqr(grad_i)
        updates.append((param_i, param_i - learning_rate * grad_i / T.sqrt(acc)))   #AdaGrad
        updates.append((acc_i, acc))    
  
    train_model = theano.function([index], [cost,layer3.errors(y)], updates=updates,
          givens={
            x_index_l: indices_train_l[index: index + batch_size],
            x_index_r: indices_train_r[index: index + batch_size],
            y: trainY[index: index + batch_size],
            left_l: trainLeftPad_l[index],
            right_l: trainRightPad_l[index],
            left_r: trainLeftPad_r[index],
            right_r: trainRightPad_r[index],
            length_l: trainLengths_l[index],
            length_r: trainLengths_r[index]}, on_unused_input='ignore')

    train_model_predict = theano.function([index], [cost_this,layer3.errors(y)],
          givens={
            x_index_l: indices_train_l[index: index + batch_size],
            x_index_r: indices_train_r[index: index + batch_size],
            y: trainY[index: index + batch_size],
            left_l: trainLeftPad_l[index],
            right_l: trainRightPad_l[index],
            left_r: trainLeftPad_r[index],
            right_r: trainRightPad_r[index],
            length_l: trainLengths_l[index],
            length_r: trainLengths_r[index]}, on_unused_input='ignore')



    ###############
    # TRAIN MODEL #
    ###############
    print '... training'
    # early-stopping parameters
    patience = 500000000000000  # look as this many examples regardless
    patience_increase = 2  # wait this much longer when a new best is
                           # found
    improvement_threshold = 0.995  # a relative improvement of this much is
                                   # considered significant
    validation_frequency = min(n_train_batches/2, patience / 2)
                                  # go through this many
                                  # minibatche before checking the network
                                  # on the validation set; in this case we
                                  # check every epoch

    best_params = None
    best_validation_loss = numpy.inf
    best_iter = 0
    test_score = 0.
    start_time = time.clock()

    epoch = 0
    done_looping = False

    while (epoch < n_epochs) and (not done_looping):
        epoch = epoch + 1
        #for minibatch_index in xrange(n_train_batches): # each batch
        minibatch_index=0
        for batch_start in train_batch_start: 
            # iter means how many batches have been runed, taking into loop
            iter = (epoch - 1) * n_train_batches + minibatch_index +1

            minibatch_index=minibatch_index+1
            #if epoch %2 ==0:
            #    batch_start=batch_start+remain_train
            #time.sleep(0.5)
            if iter%update_freq != 0:
                cost_ij, error_ij=train_model_predict(batch_start)
                #print 'cost_ij: ', cost_ij
                cost_tmp+=cost_ij
                error_sum+=error_ij
            else:
                cost_average, error_ij = train_model(batch_start)
                #print 'training @ iter = '+str(iter)+' average cost: '+str(cost_average)+' sum error: '+str(error_sum)+'/'+str(update_freq)
                error_sum=0
                cost_tmp=0#reset for the next batch
            #exit(0)
            if iter % n_train_batches == 0:
                print 'training @ iter = '+str(iter)+' average cost: '+str(cost_average)+' error: '+str(error_sum)+'/'+str(update_freq)+' error rate: '+str(error_sum*1.0/update_freq)
            #if iter ==1:
            #    exit(0)
            
            if iter % n_train_batches == 0:
                write_file=open('log.txt', 'w')
                test_losses=[]
                for i in test_batch_start:
                    test_loss, pred_y=test_model(i)
                    #test_losses = [test_model(i) for i in test_batch_start]
                    test_losses.append(test_loss)
                    write_file.write(str(pred_y[0])+'\n')#+'\t'+str(testY[i].eval())+

                write_file.close()
                test_score = numpy.mean(test_losses)
                print(('\t\t\t\t\t\tepoch %i, minibatch %i/%i, test error of best '
                           'model %f %%') %
                          (epoch, minibatch_index, n_train_batches,
                           test_score * 100.))
                '''
                #print 'validating & testing...'
                # compute zero-one loss on validation set
                validation_losses = []
                for i in dev_batch_start:
                    time.sleep(0.5)
                    validation_losses.append(validate_model(i))
                #validation_losses = [validate_model(i) for i in dev_batch_start]
                this_validation_loss = numpy.mean(validation_losses)
                print('\t\tepoch %i, minibatch %i/%i, validation error %f %%' % \
                      (epoch, minibatch_index , n_train_batches, \
                       this_validation_loss * 100.))

                # if we got the best validation score until now
                if this_validation_loss < best_validation_loss:

                    #improve patience if loss improvement is good enough
                    if this_validation_loss < best_validation_loss *  \
                       improvement_threshold:
                        patience = max(patience, iter * patience_increase)

                    # save best validation score and iteration number
                    best_validation_loss = this_validation_loss
                    best_iter = iter

                    # test it on the test set
                    test_losses = [test_model(i) for i in test_batch_start]
                    test_score = numpy.mean(test_losses)
                    print(('\t\t\t\tepoch %i, minibatch %i/%i, test error of best '
                           'model %f %%') %
                          (epoch, minibatch_index, n_train_batches,
                           test_score * 100.))
            '''

            if patience <= iter:
                done_looping = True
                break

    end_time = time.clock()
    print('Optimization complete.')
    print('Best validation score of %f %% obtained at iteration %i,'\
          'with test performance %f %%' %
          (best_validation_loss * 100., best_iter + 1, test_score * 100.))
    print >> sys.stderr, ('The code for file ' +
                          os.path.split(__file__)[1] +
                          ' ran for %.2fm' % ((end_time - start_time) / 60.))



        


if __name__ == '__main__':
    evaluate_lenet5()